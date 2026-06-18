"""Tests de la gestion du stock pharmacie via les mouvements."""
from django.test import TestCase

from pharmacie.models import Medicament, MouvementStock


class MouvementStockTests(TestCase):
    def setUp(self):
        self.med = Medicament.objects.create(
            nom='Paracétamol', quantite_stock=100, seuil_alerte=10)

    def test_entree_augmente_le_stock(self):
        MouvementStock.objects.create(
            medicament=self.med, type_mouvement='entree', quantite=50)
        self.med.refresh_from_db()
        self.assertEqual(self.med.quantite_stock, 150)

    def test_sortie_diminue_le_stock(self):
        MouvementStock.objects.create(
            medicament=self.med, type_mouvement='sortie', quantite=30)
        self.med.refresh_from_db()
        self.assertEqual(self.med.quantite_stock, 70)

    def test_suppression_annule_le_mouvement(self):
        m = MouvementStock.objects.create(
            medicament=self.med, type_mouvement='sortie', quantite=40)
        self.med.refresh_from_db()
        self.assertEqual(self.med.quantite_stock, 60)
        m.delete()
        self.med.refresh_from_db()
        self.assertEqual(self.med.quantite_stock, 100)


class StatutStockTests(TestCase):
    def setUp(self):
        self.med = Medicament.objects.create(
            nom='Amoxicilline', quantite_stock=50, seuil_alerte=10)

    def test_stock_ok(self):
        self.assertEqual(self.med.statut_stock(), 'ok')
        self.assertFalse(self.med.est_en_alerte())
        self.assertFalse(self.med.est_rupture())

    def test_stock_en_alerte_sous_le_seuil(self):
        self.med.quantite_stock = 5
        self.med.save()
        self.assertTrue(self.med.est_en_alerte())
        self.assertEqual(self.med.statut_stock(), 'alerte')

    def test_stock_en_rupture(self):
        self.med.quantite_stock = 0
        self.med.save()
        self.assertTrue(self.med.est_rupture())
        self.assertEqual(self.med.statut_stock(), 'rupture')
