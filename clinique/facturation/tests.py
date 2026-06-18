"""Tests du moteur de facturation : répartition assurance/patient et statut."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from patients.models import Patient
from facturation.models import Facture, Assurance, Paiement


def creer_patient(**kw):
    defaults = dict(
        nom='Test', prenom='Patient', sexe='Masculin',
        date_naissance=date(1990, 1, 1), adresse='Bamako',
        telephone='+223 00 00 00 00', email='t@example.com', numero_urgence='',
    )
    defaults.update(kw)
    return Patient.objects.create(**defaults)


class RepartitionAssuranceTests(TestCase):
    """part_assurance / part_patient sont des calculs purs sur montant_total + taux."""

    def test_part_assurance_et_part_patient(self):
        f = Facture(montant_total=Decimal('10000'), taux_prise_en_charge=Decimal('70'))
        self.assertEqual(f.part_assurance(), Decimal('7000'))
        self.assertEqual(f.part_patient(), Decimal('3000'))

    def test_sans_assurance_tout_a_charge_du_patient(self):
        f = Facture(montant_total=Decimal('5000'), taux_prise_en_charge=Decimal('0'))
        self.assertEqual(f.part_assurance(), Decimal('0'))
        self.assertEqual(f.part_patient(), Decimal('5000'))


class SnapshotTauxTests(TestCase):
    def setUp(self):
        self.patient = creer_patient()

    def test_taux_copie_depuis_assurance_a_la_creation(self):
        # Nom distinct : une migration de données seede déjà « AMO ».
        assurance = Assurance.objects.create(
            nom='Mutuelle Test', taux_prise_en_charge=Decimal('70'))
        f = Facture.objects.create(patient=self.patient, assurance=assurance)
        f.refresh_from_db()
        self.assertEqual(f.taux_prise_en_charge, Decimal('70'))

    def test_taux_a_zero_sans_assurance(self):
        f = Facture.objects.create(patient=self.patient)
        self.assertEqual(f.taux_prise_en_charge, Decimal('0'))


class StatutPaiementTests(TestCase):
    """Le statut dépend de la part RÉELLEMENT due par le patient (ticket modérateur)."""

    def setUp(self):
        self.patient = creer_patient()

    def _facture_avec_total(self, total, taux=Decimal('0')):
        # generer_lignes() remet montant_total à 0 sans lignes : on force la valeur.
        f = Facture.objects.create(patient=self.patient)
        Facture.objects.filter(pk=f.pk).update(
            montant_total=Decimal(total), taux_prise_en_charge=taux)
        f.refresh_from_db()
        return f

    def test_transitions_non_paye_partiel_paye(self):
        f = self._facture_avec_total('10000')
        f.update_statut()
        f.refresh_from_db()
        self.assertEqual(f.statut, 'non payé')

        Paiement.objects.create(facture=f, montant=Decimal('4000'), mode_paiement='cash')
        f.refresh_from_db()
        self.assertEqual(f.statut, 'partiel')

        Paiement.objects.create(facture=f, montant=Decimal('6000'), mode_paiement='cash')
        f.refresh_from_db()
        self.assertEqual(f.statut, 'payé')

    def test_prise_en_charge_totale_marque_paye(self):
        f = self._facture_avec_total('10000', taux=Decimal('100'))
        f.update_statut()
        f.refresh_from_db()
        self.assertEqual(f.part_patient(), Decimal('0'))
        self.assertEqual(f.statut, 'payé')
