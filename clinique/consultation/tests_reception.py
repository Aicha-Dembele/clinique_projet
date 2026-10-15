"""Tests de l'écran de réception : tout le passage d'un patient d'un coup.

Un seul envoi de formulaire doit produire la fiche patient (si elle n'existe
pas), le rendez-vous, la facture au bon tarif, l'encaissement, et amener la
caisse sur le reçu.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Rendez_vous
from facturation.models import Assurance, Facture, Paiement, Tarif
from facturation.regles import blocage, facture_de
from patients.models import Patient
from personnel.models import Medecin


@override_settings(ALLOWED_HOSTS=['testserver'])
class ReceptionTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        Tarif.objects.create(type_service='consultation', specialite='Cardiologie',
                             nom='Consultation cardiologie', prix=Decimal('5000'))
        self.medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Cardio',
            specialite='Cardiologie', role='medecin')

        utilisateur = User.objects.create_user('recept', password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur,
                              role=Role.objects.get(code='receptionniste'))
        self.client.force_login(utilisateur)

    def formulaire(self, **remplacements):
        donnees = {
            'type_patient': 'nouveau',
            'nom': 'Keita', 'prenom': 'Moussa', 'sexe': 'Masculin',
            'date_naissance': '1992-05-04', 'telephone': '70000000',
            'adresse': 'Bamako', 'numero_urgence': '70000001',
            'medecin': self.medecin.pk, 'date': '2026-12-01T09:00',
            'mode_paiement': 'cash',
        }
        donnees.update(remplacements)
        return donnees

    # ── le parcours complet, en un seul envoi ────────────────────

    def test_un_nouveau_patient_est_enregistre_facture_et_encaisse(self):
        reponse = self.client.post(reverse('consultation:reception'), self.formulaire())

        patient = Patient.objects.get(nom='Keita')
        rdv = Rendez_vous.objects.get(patient=patient)
        facture = facture_de('rendez_vous', rdv)
        paiement = Paiement.objects.get(facture=facture)

        self.assertEqual(facture.montant_total, Decimal('5000'))
        self.assertEqual(paiement.montant, Decimal('5000'))
        self.assertEqual(facture.statut, 'payé')
        # La caisse arrive sur le reçu à remettre au patient.
        self.assertRedirects(
            reponse, reverse('facturation:paiement_recu', args=[paiement.pk]))

    def test_apres_encaissement_la_consultation_est_autorisee(self):
        """Le but de l'écran : que le médecin puisse recevoir le patient."""
        self.client.post(reverse('consultation:reception'), self.formulaire())
        rdv = Rendez_vous.objects.get()

        self.assertIsNone(blocage('rendez_vous', rdv))

    def test_un_patient_deja_connu_nest_pas_recree(self):
        ancien = Patient.objects.create(
            nom='Traore', prenom='Awa', sexe='Féminin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='0000', email='a@b.c', numero_urgence='0000')

        self.client.post(reverse('consultation:reception'), self.formulaire(
            type_patient='existant', patient=ancien.pk))

        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(Rendez_vous.objects.get().patient, ancien)

    # ── le tarif et l'assurance ──────────────────────────────────

    def test_le_tarif_suit_la_specialite_du_medecin(self):
        Tarif.objects.create(type_service='consultation', specialite='Dermatologie',
                             nom='Consultation dermatologie', prix=Decimal('9000'))
        dermato = Medecin.objects.create(
            nom='Diallo', prenom='S', telephone='2', service='Derma',
            specialite='Dermatologie', role='medecin')

        self.client.post(reverse('consultation:reception'),
                         self.formulaire(medecin=dermato.pk))

        facture = Facture.objects.get()
        self.assertEqual(facture.montant_total, Decimal('9000'))

    def test_seule_la_part_patient_est_encaissee(self):
        mutuelle = Assurance.objects.create(nom='Mutuelle de test',
                                            taux_prise_en_charge=Decimal('60'))

        self.client.post(reverse('consultation:reception'),
                         self.formulaire(assurance=mutuelle.pk))

        facture = Facture.objects.get()
        paiement = Paiement.objects.get()
        self.assertEqual(facture.montant_total, Decimal('5000'))
        self.assertEqual(paiement.montant, Decimal('2000'))   # 40 % de 5 000
        self.assertEqual(facture.statut, 'payé')

    def test_un_patient_couvert_a_100_pour_cent_na_rien_a_payer(self):
        mutuelle = Assurance.objects.create(nom='Couverture totale',
                                            taux_prise_en_charge=Decimal('100'))

        reponse = self.client.post(reverse('consultation:reception'),
                                   self.formulaire(assurance=mutuelle.pk))

        facture = Facture.objects.get()
        self.assertEqual(Paiement.objects.count(), 0)
        self.assertRedirects(reponse, reverse('facturation:detail', args=[facture.pk]))
        self.assertIsNone(blocage('rendez_vous', Rendez_vous.objects.get()))

    # ── les autres modes d'encaissement ──────────────────────────

    def test_sans_encaissement_on_atterrit_sur_la_facture_a_regler(self):
        reponse = self.client.post(reverse('consultation:reception'),
                                   self.formulaire(mode_paiement=''))

        facture = Facture.objects.get()
        self.assertEqual(Paiement.objects.count(), 0)
        self.assertRedirects(reponse, reverse('facturation:detail', args=[facture.pk]))
        # Le rendez-vous existe, mais la consultation reste interdite.
        self.assertIsNotNone(blocage('rendez_vous', Rendez_vous.objects.get()))

    def test_sama_money_renvoie_vers_la_page_de_paiement(self):
        reponse = self.client.post(reverse('consultation:reception'),
                                   self.formulaire(mode_paiement='sama_money'))

        facture = Facture.objects.get()
        self.assertRedirects(
            reponse,
            f"{reverse('facturation:paiement_ajouter')}?facture={facture.pk}")

    # ── les refus ────────────────────────────────────────────────

    def test_une_fiche_incomplete_ne_cree_rien(self):
        """Ni patient à moitié créé, ni rendez-vous orphelin : tout ou rien."""
        reponse = self.client.post(reverse('consultation:reception'),
                                   self.formulaire(telephone='', prenom=''))

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(Patient.objects.count(), 0)
        self.assertEqual(Rendez_vous.objects.count(), 0)
        self.assertEqual(Facture.objects.count(), 0)

    def test_un_creneau_deja_pris_ne_laisse_pas_de_patient_orphelin(self):
        """Si le rendez-vous échoue, la fiche patient ne doit pas rester."""
        self.client.post(reverse('consultation:reception'), self.formulaire())
        avant = Patient.objects.count()

        self.client.post(reverse('consultation:reception'), self.formulaire(
            nom='Sidibe', prenom='Fanta'))   # même médecin, même créneau

        self.assertEqual(Patient.objects.count(), avant)
        self.assertFalse(Patient.objects.filter(nom='Sidibe').exists())

    def test_la_page_est_refusee_a_qui_nest_pas_de_la_reception(self):
        medecin_user = User.objects.create_user('doc', password='motdepasse-de-test')
        Profil.objects.create(user=medecin_user, role=Role.objects.get(code='medecin'),
                              medecin=self.medecin)
        self.client.force_login(medecin_user)

        reponse = self.client.get(reverse('consultation:reception'))

        self.assertNotEqual(reponse.status_code, 200)
