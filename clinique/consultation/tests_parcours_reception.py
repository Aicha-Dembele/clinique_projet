"""Tests de cohérence : toutes les portes mènent à l'encaissement.

Aïcha avait repéré l'incohérence : depuis le tableau de bord, enregistrer un
patient le laissait dans la liste des patients, alors que l'écran Réception
allait jusqu'au reçu. Trois chemins, trois fins différentes.

Désormais le parcours est le même partout : enregistrer → rendez-vous →
encaisser → reçu. Seul un bouton explicite « Enregistrer seulement » permet
d'ouvrir une fiche sans suite.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Rendez_vous
from facturation.models import Facture, Paiement, Tarif
from patients.models import Patient
from personnel.models import Medecin


@override_settings(ALLOWED_HOSTS=['testserver'])
class PortesDEntreeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        Tarif.objects.create(type_service='consultation', specialite='Généraliste',
                             nom='Consultation généraliste', prix=Decimal('3000'))
        self.medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Diag',
            specialite='Généraliste', role='medecin')

        utilisateur = User.objects.create_user('recept', password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur,
                              role=Role.objects.get(code='receptionniste'))
        self.client.force_login(utilisateur)

    def fiche_patient(self, **extra):
        donnees = {
            'nom': 'Keita', 'prenom': 'Moussa', 'sexe': 'Masculin',
            'date_naissance': '1992-05-04', 'telephone': '70000000',
            'adresse': 'Bamako', 'numero_urgence': '70000001',
        }
        donnees.update(extra)
        return donnees

    # ── porte 1 : le formulaire patient ──────────────────────────

    def test_enregistrer_un_patient_enchaine_sur_la_reception(self):
        reponse = self.client.post(reverse('patients:ajouter'), self.fiche_patient())

        patient = Patient.objects.get(nom='Keita')
        self.assertRedirects(
            reponse,
            f"{reverse('consultation:reception')}?patient={patient.pk}",
            fetch_redirect_response=False)

    def test_le_patient_arrive_deja_selectionne_sur_la_reception(self):
        self.client.post(reverse('patients:ajouter'), self.fiche_patient())
        patient = Patient.objects.get(nom='Keita')

        reponse = self.client.get(
            f"{reverse('consultation:reception')}?patient={patient.pk}")

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context['patient_pre'], str(patient.pk))
        self.assertContains(reponse, f'value="{patient.pk}" selected')

    def test_enregistrer_seulement_reste_possible(self):
        """Le cas rare : ouvrir une fiche sans que le patient soit reçu."""
        reponse = self.client.post(reverse('patients:ajouter'),
                                   self.fiche_patient(sans_suite='1'))

        patient = Patient.objects.get(nom='Keita')
        self.assertRedirects(
            reponse, f"{reverse('patients:liste')}?new={patient.pk}",
            fetch_redirect_response=False)

    # ── porte 2 : le rendez-vous seul ────────────────────────────

    def test_creer_un_rendez_vous_mene_a_la_facture_a_encaisser(self):
        patient = Patient.objects.create(
            nom='Traore', prenom='Awa', sexe='Féminin',
            date_naissance='1990-01-01', adresse='Bamako',
            telephone='0000', email='a@b.c', numero_urgence='0000')

        reponse = self.client.post(reverse('consultation:rdv_ajouter'), {
            'patient': patient.pk, 'medecin': self.medecin.pk,
            'date': '2026-12-01T09:00', 'statut': 'programme',
        })

        facture = Facture.objects.get(rendez_vous=Rendez_vous.objects.get())
        self.assertRedirects(reponse,
                             reverse('facturation:detail', args=[facture.pk]))

    def test_un_patient_couvert_a_100_pour_cent_ne_passe_pas_par_la_caisse(self):
        from facturation.models import Assurance

        couvert = Patient.objects.create(
            nom='Diarra', prenom='Fanta', sexe='Féminin',
            date_naissance='1990-01-01', adresse='Bamako',
            telephone='0001', email='f@d.c', numero_urgence='0001',
            assurance=Assurance.objects.create(nom='Couverture totale',
                                               taux_prise_en_charge=Decimal('100')))

        reponse = self.client.post(reverse('consultation:rdv_ajouter'), {
            'patient': couvert.pk, 'medecin': self.medecin.pk,
            'date': '2026-12-02T09:00', 'statut': 'programme',
        })

        self.assertRedirects(reponse, reverse('consultation:rdv_liste'))

    # ── porte 3 : la réception, inchangée ────────────────────────

    def test_la_reception_mene_toujours_au_recu(self):
        reponse = self.client.post(reverse('consultation:reception'), {
            'type_patient': 'nouveau', **self.fiche_patient(),
            'medecin': self.medecin.pk, 'date': '2026-12-03T09:00',
            'mode_paiement': 'cash',
        })

        paiement = Paiement.objects.get()
        self.assertRedirects(
            reponse, reverse('facturation:paiement_recu', args=[paiement.pk]))

    # ── le tableau de bord pointe au bon endroit ─────────────────

    def test_le_tableau_de_bord_propose_la_reception_en_premier(self):
        reponse = self.client.get(reverse('dashboard'))

        self.assertContains(reponse, reverse('consultation:reception'))
