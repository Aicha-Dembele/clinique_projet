"""Tests de la remise du reçu.

Règle visée : après chaque encaissement, la caisse arrive directement sur le
reçu à remettre au patient — elle n'a pas à aller le chercher dans la liste
des paiements.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Rendez_vous
from facturation.models import Facture, Paiement, Tarif
from facturation.regles import facturer
from patients.models import Patient
from personnel.models import Medecin


@override_settings(ALLOWED_HOSTS=['testserver'])
class RecuApresPaiementTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()   # le catalogue des rôles et de leurs permissions

    def setUp(self):
        Tarif.objects.create(type_service='consultation', specialite='Généraliste',
                             nom='Consultation généraliste', prix=Decimal('3000'))
        medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Diag',
            specialite='Généraliste', role='medecin')
        patient = Patient.objects.create(
            nom='Traore', prenom='Awa', sexe='Féminin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='0000', email='a@b.c', numero_urgence='0000')

        rdv = Rendez_vous.objects.create(
            patient=patient, medecin=medecin, date='2026-12-01T09:00')
        self.facture = facturer(patient, 'rendez_vous', rdv)

        utilisateur = User.objects.create_user('caisse', password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur,
                              role=Role.objects.get(code='receptionniste'))
        self.client.force_login(utilisateur)

    def test_encaisser_mene_droit_au_recu(self):
        reponse = self.client.post(reverse('facturation:paiement_ajouter'), {
            'facture': self.facture.pk, 'montant': '3000',
            'mode_paiement': 'cash', 'note': '',
        })

        paiement = Paiement.objects.get(facture=self.facture)
        self.assertRedirects(
            reponse, reverse('facturation:paiement_recu', args=[paiement.pk]))

    def test_le_recu_affiche_le_patient(self):
        paiement = Paiement.objects.create(
            facture=self.facture, montant=Decimal('3000'), mode_paiement='cash')

        reponse = self.client.get(
            reverse('facturation:paiement_recu', args=[paiement.pk]))

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Traore')

    def test_le_recu_propose_de_revenir_a_la_facture(self):
        paiement = Paiement.objects.create(
            facture=self.facture, montant=Decimal('3000'), mode_paiement='cash')

        reponse = self.client.get(
            reverse('facturation:paiement_recu', args=[paiement.pk]))

        self.assertContains(
            reponse, reverse('facturation:detail', args=[self.facture.pk]))

    def test_le_recu_existe_aussi_en_pdf(self):
        paiement = Paiement.objects.create(
            facture=self.facture, montant=Decimal('3000'), mode_paiement='cash')

        reponse = self.client.get(
            reverse('facturation:paiement_pdf', args=[paiement.pk]))

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse['Content-Type'], 'application/pdf')
