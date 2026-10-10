"""Tests des lots : chaque arrivage garde sa péremption, et on sert le plus urgent.

Le défaut corrigé : avant les lots, la date de péremption était portée par le
médicament. Réapprovisionner écrasait la date de l'ancien stock, qui devenait
invisible et qu'on découvrait périmé.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from pharmacie.models import Fournisseur, Lot, Medicament, MouvementStock, SortieLot


@override_settings(ALLOWED_HOSTS=['testserver'])
class LotsTests(TestCase):

    def setUp(self):
        # Les migrations installent le catalogue réel : on part d'un
        # catalogue vide pour que ces tests portent sur les lots.
        Medicament.objects.all().delete()
        self.medicament = Medicament.objects.create(
            nom='Paracétamol', dci='Paracétamol', unite='boîte',
            prix_unitaire=Decimal('500'), seuil_alerte=5)

    def approvisionner(self, quantite, perime_dans_jours=None, numero='',
                       prix_achat=None, fournisseur=None):
        mouvement = MouvementStock(
            medicament=self.medicament, type_mouvement='entree',
            quantite=quantite, prix_unitaire=Decimal('500'))
        mouvement.lot_numero = numero
        if perime_dans_jours is not None:
            mouvement.lot_peremption = timezone.localdate() + timedelta(days=perime_dans_jours)
        mouvement.lot_prix_achat = prix_achat
        mouvement.lot_fournisseur = fournisseur
        mouvement.save()
        return mouvement

    def servir(self, quantite):
        return MouvementStock.objects.create(
            medicament=self.medicament, type_mouvement='sortie', quantite=quantite)

    def rafraichi(self):
        return Medicament.objects.get(pk=self.medicament.pk)

    # ── l'entrée crée un lot ─────────────────────────────────────

    def test_toute_entree_cree_un_lot(self):
        self.approvisionner(100, perime_dans_jours=400, numero='AB123',
                            prix_achat=Decimal('300'))

        lot = Lot.objects.get()
        self.assertEqual(lot.numero, 'AB123')
        self.assertEqual(lot.quantite_initiale, 100)
        self.assertEqual(lot.quantite_restante, 100)
        self.assertEqual(lot.prix_achat, Decimal('300'))
        self.assertEqual(self.rafraichi().quantite_stock, 100)

    def test_le_lot_retient_son_fournisseur(self):
        grossiste = Fournisseur.objects.create(nom='Pharmadis Bamako')

        self.approvisionner(50, perime_dans_jours=200, fournisseur=grossiste)

        self.assertEqual(Lot.objects.get().fournisseur, grossiste)

    # ── le défaut corrigé ────────────────────────────────────────

    def test_reapprovisionner_nefface_plus_la_peremption_de_lancien_stock(self):
        """Le cœur du problème : 100 boîtes périment bientôt, 200 arrivent
        avec une date lointaine. L'échéance proche doit rester visible."""
        self.approvisionner(100, perime_dans_jours=20)    # ancien stock
        self.approvisionner(200, perime_dans_jours=700)   # arrivage neuf

        medicament = self.rafraichi()
        self.assertEqual(medicament.quantite_stock, 300)
        # La date retenue est celle du lot le plus urgent, pas du dernier reçu.
        self.assertEqual(medicament.date_peremption,
                         timezone.localdate() + timedelta(days=20))
        self.assertTrue(medicament.bientot_perime())

    # ── servir le lot le plus urgent (PEPS / FEFO) ───────────────

    def test_on_sert_dabord_le_lot_qui_perime_le_plus_tot(self):
        self.approvisionner(100, perime_dans_jours=700, numero='LOINTAIN')
        self.approvisionner(50, perime_dans_jours=20, numero='URGENT')

        self.servir(30)

        urgent = Lot.objects.get(numero='URGENT')
        lointain = Lot.objects.get(numero='LOINTAIN')
        self.assertEqual(urgent.quantite_restante, 20)      # entamé
        self.assertEqual(lointain.quantite_restante, 100)   # intact

    def test_une_sortie_peut_vider_un_lot_et_entamer_le_suivant(self):
        self.approvisionner(30, perime_dans_jours=20, numero='URGENT')
        self.approvisionner(100, perime_dans_jours=700, numero='LOINTAIN')

        mouvement = self.servir(50)

        self.assertEqual(Lot.objects.get(numero='URGENT').quantite_restante, 0)
        self.assertEqual(Lot.objects.get(numero='LOINTAIN').quantite_restante, 80)
        # Le détail est conservé : on sait quel lot est parti, et combien.
        detail = {s.lot.numero: s.quantite for s in mouvement.lots_servis.all()}
        self.assertEqual(detail, {'URGENT': 30, 'LOINTAIN': 20})

    def test_la_peremption_se_met_a_jour_quand_un_lot_sepuise(self):
        self.approvisionner(30, perime_dans_jours=20, numero='URGENT')
        self.approvisionner(100, perime_dans_jours=700, numero='LOINTAIN')
        self.assertEqual(self.rafraichi().date_peremption,
                         timezone.localdate() + timedelta(days=20))

        self.servir(30)   # le lot urgent est épuisé

        self.assertEqual(self.rafraichi().date_peremption,
                         timezone.localdate() + timedelta(days=700))

    def test_un_lot_sans_date_est_servi_en_dernier(self):
        """On écoule d'abord ce dont on connaît l'échéance."""
        self.approvisionner(50, numero='SANS-DATE')
        self.approvisionner(50, perime_dans_jours=300, numero='DATE')

        self.servir(50)

        self.assertEqual(Lot.objects.get(numero='DATE').quantite_restante, 0)
        self.assertEqual(Lot.objects.get(numero='SANS-DATE').quantite_restante, 50)

    # ── cohérence avec le compteur ───────────────────────────────

    def test_les_lots_collent_toujours_au_compteur(self):
        self.approvisionner(100, perime_dans_jours=50)
        self.approvisionner(60, perime_dans_jours=400)
        self.servir(75)
        self.servir(20)

        medicament = self.rafraichi()
        self.assertEqual(medicament.quantite_stock, 65)
        self.assertEqual(medicament.stock_par_lots(), 65)

    def test_une_sortie_non_couverte_par_les_lots_ne_bloque_pas(self):
        """Stock d'avant les lots : le compteur reste la référence."""
        Medicament.objects.filter(pk=self.medicament.pk).update(quantite_stock=40)

        self.servir(10)   # aucun lot en base

        self.assertEqual(self.rafraichi().quantite_stock, 30)
        self.assertEqual(SortieLot.objects.count(), 0)


@override_settings(ALLOWED_HOSTS=['testserver'])
class LotInitialTests(TestCase):
    """La migration qui donne un lot au stock déjà en place."""

    def test_le_catalogue_livre_avec_les_migrations_a_ses_lots(self):
        en_stock = Medicament.objects.filter(quantite_stock__gt=0)

        self.assertTrue(en_stock.exists())
        for medicament in en_stock:
            with self.subTest(medicament=medicament.nom):
                self.assertEqual(medicament.stock_par_lots(),
                                 medicament.quantite_stock)
