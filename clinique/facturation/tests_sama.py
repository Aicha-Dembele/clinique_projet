"""Le paiement SAMA Money : le client d'API, et le parcours de caisse.

Règle tenue par tous ces tests : **aucun paiement n'est écrit en base tant
que le patient n'a pas confirmé**. Enregistrer avant la confirmation
reviendrait à inscrire en caisse un argent qui n'est pas arrivé.

Aucun test ne sort sur le réseau : soit on est en mode démonstration (pas
de clé), soit `requests.request` est remplacé par une fausse réponse.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Rendez_vous
from facturation import sama
from facturation.models import Paiement, Tarif
from facturation.regles import facturer
from patients.models import Patient
from personnel.models import Medecin


class FausseReponse:
    """Ce que `requests.request` rend, en juste assez détaillé."""

    def __init__(self, corps, code=200):
        self._corps = corps
        self.status_code = code

    def json(self):
        return self._corps


@override_settings(SAMA_MONEY_CLE_API='')
class ClientSansCleTests(TestCase):
    """Sans clé configurée : aucune requête ne part, la démo fonctionne."""

    def test_le_mode_demonstration_est_actif(self):
        self.assertTrue(sama.mode_demonstration())

    @patch('facturation.sama.requests.request')
    def test_aucune_requete_reseau_nest_envoyee(self, appel):
        sama.demander_encaissement('76000000', 5000)

        appel.assert_not_called()

    def test_lencaissement_part_en_attente(self):
        """Même en démonstration : on n'encaisse pas avant la confirmation."""
        encaissement = sama.demander_encaissement('76000000', 5000)

        self.assertEqual(encaissement['status'], sama.EN_ATTENTE)
        self.assertEqual(encaissement['amount_xof'], 5000)

    def test_la_confirmation_reussit(self):
        encaissement = sama.demander_encaissement('76000000', 5000)

        etat = sama.lire_encaissement(encaissement['reference'])

        self.assertEqual(etat['status'], sama.REUSSI)

    def test_le_numero_de_refus_fait_echouer(self):
        """Pour montrer au jury que le refus est traité, pas seulement le succès."""
        encaissement = sama.demander_encaissement(sama.NUMERO_REFUS_DEMO, 5000)

        etat = sama.lire_encaissement(encaissement['reference'])

        self.assertEqual(etat['status'], sama.ECHOUE)

    def test_numero_trop_court_refuse(self):
        with self.assertRaises(sama.ErreurSama):
            sama.demander_encaissement('123', 5000)

    def test_montant_nul_refuse(self):
        with self.assertRaises(sama.ErreurSama):
            sama.demander_encaissement('76000000', 0)


@override_settings(SAMA_MONEY_CLE_API='cle_de_test',
                   SAMA_MONEY_BASE_URL='https://api.sama.money/v1')
class ClientAvecCleTests(TestCase):
    """Avec une clé : on vérifie ce qui part vraiment sur le réseau."""

    @patch('facturation.sama.requests.request')
    def test_lappel_suit_la_documentation(self, appel):
        appel.return_value = FausseReponse(
            {'reference': 'chg_1', 'status': sama.EN_ATTENTE})

        sama.demander_encaissement('76000000', 5000,
                                   description='Consultation', reference='FAC-0001')

        methode, url = appel.call_args[0]
        options = appel.call_args[1]
        self.assertEqual(methode, 'POST')
        self.assertEqual(url, 'https://api.sama.money/v1/charges')
        self.assertEqual(options['json'], {
            'client_phone': '76000000',
            'amount_xof': 5000,
            'description': 'Consultation',
            'reference': 'FAC-0001',
        })
        self.assertEqual(options['headers']['Authorization'], 'Bearer cle_de_test')
        # Rejouer la requête ne doit pas débiter deux fois.
        self.assertIn('Idempotency-Key', options['headers'])

    @patch('facturation.sama.requests.request')
    def test_la_relecture_interroge_la_bonne_adresse(self, appel):
        appel.return_value = FausseReponse({'status': sama.REUSSI})

        sama.lire_encaissement('chg_42')

        methode, url = appel.call_args[0]
        self.assertEqual(methode, 'GET')
        self.assertEqual(url, 'https://api.sama.money/v1/charges/chg_42')

    @patch('facturation.sama.requests.request')
    def test_une_erreur_de_lapi_devient_une_erreur_lisible(self, appel):
        appel.return_value = FausseReponse(
            {'error': {'code': 'insufficient_funds'}}, code=402)

        with self.assertRaises(sama.ErreurSama) as leve:
            sama.demander_encaissement('76000000', 5000)

        self.assertIn('insufficient_funds', str(leve.exception))

    @patch('facturation.sama.requests.request')
    def test_un_service_injoignable_ne_bloque_pas_la_caisse(self, appel):
        import requests as lib
        appel.side_effect = lib.Timeout()

        with self.assertRaises(sama.ErreurSama) as leve:
            sama.demander_encaissement('76000000', 5000)

        self.assertIn('espèces', str(leve.exception))


@override_settings(ALLOWED_HOSTS=['testserver'], SAMA_MONEY_CLE_API='')
class ParcoursDeCaisseTests(TestCase):
    """De la facture au reçu, par l'écran de la caisse."""

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        # Une facture n'a de montant que par ses lignes, et ses lignes
        # viennent de la prestation facturée : on monte donc un vrai
        # rendez-vous au tarif, comme le fait tests_caisses.py. Une facture
        # créée à vide retomberait à 0 et passerait pour déjà réglée.
        Tarif.objects.create(type_service='consultation', specialite='Généraliste',
                             nom='Consultation généraliste', prix=Decimal('5000'))
        medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Diag',
            specialite='Généraliste', role='medecin')
        self.patient = Patient.objects.create(
            nom='Keita', prenom='Moussa', sexe='Masculin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='70000000', email='k@example.com', numero_urgence='70000001')
        rdv = Rendez_vous.objects.create(
            patient=self.patient, medecin=medecin, date='2026-12-01T09:00')
        self.facture = facturer(self.patient, 'rendez_vous', rdv)

        utilisateur = User.objects.create_user('recept', password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur,
                              role=Role.objects.get(code='receptionniste'))
        self.client.force_login(utilisateur)

    def choisir_sama(self):
        return self.client.post(reverse('facturation:paiement_ajouter'), {
            'facture': self.facture.pk, 'montant': '5000',
            'mode_paiement': 'sama_money', 'note': 'Essai',
        })

    def test_le_mode_sama_mene_a_lecran_dedie(self):
        reponse = self.choisir_sama()

        self.assertRedirects(reponse, reverse('facturation:paiement_sama_money'))
        self.assertEqual(Paiement.objects.count(), 0)

    def test_la_demande_ne_cree_aucun_paiement(self):
        """Le coeur de la regle : demander n'est pas encaisser."""
        self.choisir_sama()

        reponse = self.client.post(reverse('facturation:paiement_sama_money'),
                                   {'numero': '76000000'})

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(Paiement.objects.count(), 0)
        self.assertEqual(self.client.session['paiement_sama']['encaissement']['numero'],
                         '76000000')

    def test_le_paiement_nait_a_la_confirmation(self):
        self.choisir_sama()
        self.client.post(reverse('facturation:paiement_sama_money'),
                         {'numero': '76000000'})

        self.client.post(reverse('facturation:paiement_sama_money'), {'verifier': '1'})

        paiement = Paiement.objects.get()
        self.assertEqual(paiement.mode_paiement, 'sama_money')
        self.assertEqual(paiement.montant, Decimal('5000'))
        # La trace porte la reference SAMA et le numero masque.
        self.assertIn('SAMA Money', paiement.note)
        self.assertIn('76', paiement.note)
        self.assertNotIn('76000000', paiement.note)

    def test_un_refus_ne_laisse_aucun_paiement(self):
        self.choisir_sama()
        self.client.post(reverse('facturation:paiement_sama_money'),
                         {'numero': sama.NUMERO_REFUS_DEMO})

        reponse = self.client.post(reverse('facturation:paiement_sama_money'),
                                   {'verifier': '1'})

        self.assertEqual(Paiement.objects.count(), 0)
        self.assertContains(reponse, 'refusé')

    def test_verifier_sans_avoir_demande_est_refuse(self):
        self.choisir_sama()

        reponse = self.client.post(reverse('facturation:paiement_sama_money'),
                                   {'verifier': '1'})

        self.assertEqual(Paiement.objects.count(), 0)
        # Sans apostrophe dans l'assertion : Django l'échappe en &#x27; dans
        # la page, et assertContains compare le HTML brut.
        self.assertContains(reponse, 'Demandez')

    def test_recharger_apres_confirmation_ne_double_pas_le_paiement(self):
        """La session est vidée : un rechargement ne peut pas réencaisser."""
        self.choisir_sama()
        self.client.post(reverse('facturation:paiement_sama_money'),
                         {'numero': '76000000'})
        self.client.post(reverse('facturation:paiement_sama_money'), {'verifier': '1'})

        self.client.post(reverse('facturation:paiement_sama_money'), {'verifier': '1'})

        self.assertEqual(Paiement.objects.count(), 1)

    def test_lecran_arrive_sans_facture_choisie(self):
        reponse = self.client.get(reverse('facturation:paiement_sama_money'))

        self.assertRedirects(reponse, reverse('facturation:paiement_ajouter'))


class ModesDePaiementTests(TestCase):

    def test_il_ne_reste_que_les_especes_et_sama(self):
        codes = [code for code, _ in Paiement.MODE_CHOICES]

        self.assertEqual(codes, ['cash', 'sama_money'])

    def test_orange_money_et_la_carte_ont_disparu(self):
        codes = [code for code, _ in Paiement.MODE_CHOICES]

        self.assertNotIn('orange_money', codes)
        self.assertNotIn('carte', codes)
