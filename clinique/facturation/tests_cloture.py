"""La clôture de caisse : compter le tiroir, et assumer l'écart.

Trois règles tenues ici :

  - un paiement appartient à UNE clôture, jamais deux, jamais zéro ;
  - l'argent électronique ne se compte pas — SAMA Money est tracé, l'écart
    ne peut naître que sur les espèces ;
  - un écart non expliqué n'est pas une clôture, c'est un trou : le serveur
    refuse, pas seulement le navigateur.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import JournalAudit, Profil, Role
from comptes.roles import installer_roles
from consultation.models import Consultation, Ordonnance, Rendez_vous
from facturation.models import ClotureCaisse, Facture, Paiement, Tarif
from facturation.regles import facturer
from patients.models import Patient
from personnel.models import Medecin


class BaseCaisse(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        Tarif.objects.create(type_service='consultation', specialite='Généraliste',
                             nom='Consultation', prix=Decimal('5000'))
        self.medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Gen',
            specialite='Généraliste', role='medecin')
        self.patient = Patient.objects.create(
            nom='Keita', prenom='Moussa', sexe='Masculin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='70000000', email='k@example.com', numero_urgence='70000001')

    #: Rendez_vous impose unique_together('medecin', 'date') : un médecin ne
    #: peut pas avoir deux rendez-vous au même instant. Chaque facture de
    #: test prend donc une heure différente.
    _heure = 8

    def facture_de_soins(self):
        type(self)._heure += 1
        rdv = Rendez_vous.objects.create(
            patient=self.patient, medecin=self.medecin,
            date=f'2026-12-01T{self._heure:02d}:00')
        return facturer(self.patient, 'rendez_vous', rdv)

    def encaisser(self, montant, mode='cash', facture=None):
        return Paiement.objects.create(
            facture=facture or self.facture_de_soins(),
            montant=Decimal(montant), mode_paiement=mode)

    def connecter(self, role_code):
        utilisateur = User.objects.create_user(role_code, password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur, role=Role.objects.get(code=role_code))
        self.client.force_login(utilisateur)
        return utilisateur


class ApercuTests(BaseCaisse):
    """Ce que la caisse devrait contenir, avant que quiconque ne compte."""

    def test_les_especes_et_le_sama_sont_separes(self):
        self.encaisser(5000, 'cash')
        self.encaisser(3000, 'sama_money')

        etat = ClotureCaisse.apercu('reception')

        self.assertEqual(etat['especes'], Decimal('5000'))
        self.assertEqual(etat['sama'], Decimal('3000'))
        self.assertEqual(etat['total'], Decimal('8000'))
        self.assertEqual(etat['nb'], 2)

    def test_une_caisse_vide_rend_zero(self):
        etat = ClotureCaisse.apercu('reception')

        self.assertEqual(etat['nb'], 0)
        self.assertEqual(etat['total'], Decimal('0'))

    def test_chaque_caisse_ne_voit_que_la_sienne(self):
        """Les médicaments se règlent au comptoir, les soins à la réception."""
        self.encaisser(5000, 'cash')

        self.assertEqual(ClotureCaisse.apercu('reception')['nb'], 1)
        self.assertEqual(ClotureCaisse.apercu('pharmacie')['nb'], 0)


class ClotureTests(BaseCaisse):

    def test_le_compte_juste(self):
        self.encaisser(5000, 'cash')
        self.encaisser(3000, 'sama_money')
        utilisateur = self.connecter('receptionniste')

        cloture = ClotureCaisse.cloturer(
            'reception', utilisateur, especes_comptees=5000)

        self.assertTrue(cloture.est_juste())
        self.assertEqual(cloture.ecart, Decimal('0'))
        self.assertEqual(cloture.total_especes, Decimal('5000'))
        self.assertEqual(cloture.total_sama, Decimal('3000'))
        self.assertEqual(cloture.nb_paiements, 2)

    def test_le_fond_de_caisse_entre_dans_le_calcul(self):
        self.encaisser(5000, 'cash')
        utilisateur = self.connecter('receptionniste')

        cloture = ClotureCaisse.cloturer(
            'reception', utilisateur, especes_comptees=7000, fond_de_caisse=2000)

        self.assertEqual(cloture.especes_attendues(), Decimal('7000'))
        self.assertTrue(cloture.est_juste())

    def test_un_manque_est_enregistre_et_signale(self):
        self.encaisser(5000, 'cash')
        utilisateur = self.connecter('receptionniste')

        cloture = ClotureCaisse.cloturer(
            'reception', utilisateur, especes_comptees=4500,
            commentaire='Monnaie rendue en trop ce matin')

        self.assertEqual(cloture.ecart, Decimal('-500'))
        self.assertTrue(cloture.manque())
        self.assertFalse(cloture.est_juste())
        self.assertIn('Monnaie rendue', cloture.commentaire)

    def test_un_excedent_aussi(self):
        self.encaisser(5000, 'cash')
        utilisateur = self.connecter('receptionniste')

        cloture = ClotureCaisse.cloturer(
            'reception', utilisateur, especes_comptees=5200,
            commentaire='Un patient a refusé sa monnaie')

        self.assertEqual(cloture.ecart, Decimal('200'))
        self.assertFalse(cloture.manque())

    def test_un_ecart_sans_explication_est_refuse(self):
        """La règle qui fait tout tenir : un trou doit être nommé."""
        self.encaisser(5000, 'cash')
        utilisateur = self.connecter('receptionniste')

        with self.assertRaises(ValueError) as leve:
            ClotureCaisse.cloturer('reception', utilisateur,
                                   especes_comptees=4500, commentaire='   ')

        self.assertIn('expliqué', str(leve.exception))
        self.assertEqual(ClotureCaisse.objects.count(), 0)

    def test_une_caisse_vide_ne_se_cloture_pas(self):
        utilisateur = self.connecter('receptionniste')

        with self.assertRaises(ValueError):
            ClotureCaisse.cloturer('reception', utilisateur, especes_comptees=0)

    def test_le_sama_ne_cree_jamais_decart(self):
        """L'argent électronique est tracé : on le totalise, on ne le compte pas."""
        self.encaisser(9000, 'sama_money')
        utilisateur = self.connecter('receptionniste')

        cloture = ClotureCaisse.cloturer(
            'reception', utilisateur, especes_comptees=0)

        self.assertEqual(cloture.total_sama, Decimal('9000'))
        self.assertTrue(cloture.est_juste())


class DecoupageTests(BaseCaisse):
    """Un paiement appartient à une clôture, et à une seule."""

    def test_les_paiements_sont_rattaches_a_la_cloture(self):
        self.encaisser(5000, 'cash')
        utilisateur = self.connecter('receptionniste')

        cloture = ClotureCaisse.cloturer(
            'reception', utilisateur, especes_comptees=5000)

        self.assertEqual(cloture.paiements.count(), 1)
        self.assertEqual(Paiement.objects.get().cloture, cloture)

    def test_la_cloture_suivante_ne_reprend_pas_les_memes(self):
        self.encaisser(5000, 'cash')
        utilisateur = self.connecter('receptionniste')
        ClotureCaisse.cloturer('reception', utilisateur, especes_comptees=5000)

        self.assertEqual(ClotureCaisse.apercu('reception')['nb'], 0)

    def test_le_changement_dequipe_se_gere_tout_seul(self):
        """Deux caissières sur le même tiroir, chacune arrête ce qu'elle a pris."""
        self.encaisser(5000, 'cash')
        premiere = self.connecter('receptionniste')
        ClotureCaisse.cloturer('reception', premiere, especes_comptees=5000)

        self.encaisser(3000, 'cash')
        seconde = User.objects.create_user('recept2', password='motdepasse-de-test')
        Profil.objects.create(user=seconde,
                              role=Role.objects.get(code='receptionniste'))
        deuxieme = ClotureCaisse.cloturer('reception', seconde,
                                          especes_comptees=3000)

        self.assertEqual(deuxieme.nb_paiements, 1)
        self.assertEqual(deuxieme.total_especes, Decimal('3000'))

    def test_les_montants_sont_figes(self):
        """Corriger un paiement après coup ne doit pas réécrire la clôture."""
        paiement = self.encaisser(5000, 'cash')
        utilisateur = self.connecter('receptionniste')
        cloture = ClotureCaisse.cloturer(
            'reception', utilisateur, especes_comptees=5000)

        paiement.montant = Decimal('9999')
        paiement.save()

        cloture.refresh_from_db()
        self.assertEqual(cloture.total_especes, Decimal('5000'))


@override_settings(ALLOWED_HOSTS=['testserver'])
class EcranClotureTests(BaseCaisse):

    def test_la_reception_voit_sa_caisse(self):
        self.encaisser(5000, 'cash')
        self.connecter('receptionniste')

        reponse = self.client.get(reverse('facturation:cloture_caisse'))

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context['caisse'], 'reception')
        self.assertEqual(reponse.context['etat']['especes'], Decimal('5000'))

    def test_un_medecin_ne_cloture_aucune_caisse(self):
        self.connecter('medecin')

        reponse = self.client.get(reverse('facturation:cloture_caisse'))

        self.assertEqual(reponse.status_code, 302)

    def test_cloturer_par_le_formulaire(self):
        self.encaisser(5000, 'cash')
        self.connecter('receptionniste')

        reponse = self.client.post(reverse('facturation:cloture_caisse'), {
            'especes_comptees': '5000', 'fond_de_caisse': '0',
        })

        self.assertRedirects(reponse, reverse('facturation:clotures'))
        self.assertTrue(ClotureCaisse.objects.get().est_juste())

    def test_le_formulaire_refuse_un_ecart_muet(self):
        self.encaisser(5000, 'cash')
        self.connecter('receptionniste')

        reponse = self.client.post(reverse('facturation:cloture_caisse'), {
            'especes_comptees': '4000', 'fond_de_caisse': '0', 'commentaire': '',
        })

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(ClotureCaisse.objects.count(), 0)

    def test_laudit_garde_la_trace(self):
        self.encaisser(5000, 'cash')
        utilisateur = self.connecter('receptionniste')

        self.client.post(reverse('facturation:cloture_caisse'),
                         {'especes_comptees': '5000'})

        trace = JournalAudit.objects.filter(modele='ClotureCaisse').first()
        self.assertIsNotNone(trace)
        self.assertEqual(trace.user, utilisateur)

    def test_lhistorique_compte_les_ecarts(self):
        self.encaisser(5000, 'cash')
        utilisateur = self.connecter('receptionniste')
        ClotureCaisse.cloturer('reception', utilisateur, especes_comptees=4500,
                               commentaire='Erreur de monnaie')

        reponse = self.client.get(reverse('facturation:clotures'))

        self.assertEqual(reponse.context['nb_ecarts'], 1)
        self.assertEqual(reponse.context['total_manquant'], Decimal('-500'))
        self.assertContains(reponse, 'Erreur de monnaie')
