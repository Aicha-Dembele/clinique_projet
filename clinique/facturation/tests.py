"""Tests du moteur de facturation : répartition assurance/patient et statut."""
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.contrib.auth.models import User

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


@override_settings(ALLOWED_HOSTS=['testserver'])
class RecherchePaiementsTests(TestCase):
    """La barre de recherche des paiements filtre par patient (multi-mots)."""

    def setUp(self):
        self.dupont = creer_patient(nom='Dupont', prenom='Jean')
        self.martin = creer_patient(nom='Martin', prenom='Lucie')
        f1 = Facture.objects.create(patient=self.dupont)
        f2 = Facture.objects.create(patient=self.martin)
        self.p_dupont = Paiement.objects.create(facture=f1, montant=Decimal('1000'), mode_paiement='cash')
        self.p_martin = Paiement.objects.create(facture=f2, montant=Decimal('2000'), mode_paiement='cash')

        boss = User.objects.create_superuser('boss', 'b@b.c', 'x')
        self.client.force_login(boss)

    def test_recherche_par_nom_complet(self):
        r = self.client.get('/facturation/paiements/', {'q': 'Dupont Jean'})
        self.assertEqual(r.status_code, 200)
        pks = [p.pk for p in r.context['paiements']]
        self.assertEqual(pks, [self.p_dupont.pk])

    def test_sans_recherche_tout_visible(self):
        r = self.client.get('/facturation/paiements/')
        pks = [p.pk for p in r.context['paiements']]
        self.assertIn(self.p_dupont.pk, pks)
        self.assertIn(self.p_martin.pk, pks)


@override_settings(ALLOWED_HOSTS=['testserver'])
class FacturePdfTests(TestCase):
    """Le PDF de facture se génère et embarque le logo de la clinique."""

    def test_logo_est_resolu(self):
        from django.contrib.staticfiles import finders
        from facturation.pdf import LOGO_STATIC
        self.assertIsNotNone(finders.find(LOGO_STATIC), "logo introuvable dans les statiques")

    def test_pdf_genere_valide(self):
        from facturation.pdf import facture_pdf_response
        patient = creer_patient(nom='Diallo', prenom='Mami')
        facture = Facture.objects.create(patient=patient, montant_total=Decimal('15000'))
        resp = facture_pdf_response(facture)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))
        self.assertGreater(len(resp.content), 2000)


@override_settings(ALLOWED_HOSTS=['testserver'])
class PaiementPdfTests(TestCase):
    """Le reçu de paiement se génère en PDF avec le logo de la clinique."""

    def test_pdf_recu_genere_valide(self):
        from facturation.pdf import paiement_pdf_response
        patient = creer_patient(nom='Diallo', prenom='Mami')
        facture = Facture.objects.create(patient=patient, montant_total=Decimal('20000'))
        paiement = Paiement.objects.create(
            facture=facture, montant=Decimal('20000'), mode_paiement='cash')
        resp = paiement_pdf_response(paiement)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertTrue(resp.content.startswith(b'%PDF'))
        self.assertGreater(len(resp.content), 2000)

    def test_route_pdf_paiement(self):
        patient = creer_patient(nom='Sow', prenom='B')
        facture = Facture.objects.create(patient=patient, montant_total=Decimal('5000'))
        paiement = Paiement.objects.create(
            facture=facture, montant=Decimal('5000'), mode_paiement='carte')
        boss = User.objects.create_superuser('boss', 'b@b.c', 'x')
        self.client.force_login(boss)
        r = self.client.get(f'/facturation/paiements/{paiement.pk}/pdf/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
