"""Tests de l'approvisionnement : fournisseurs, commandes, réception.

Le circuit complet que décrivait Aïcha : la clinique commande chez un
fournisseur, reçoit la livraison, et la marchandise entre en stock avec son
lot et sa date de péremption.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from pharmacie.models import (
    Commande, Fournisseur, LigneCommande, Lot, Medicament, MouvementStock)


@override_settings(ALLOWED_HOSTS=['testserver'])
class CommandeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        Medicament.objects.all().delete()
        self.fournisseur = Fournisseur.objects.create(
            nom='Pharmadis Bamako', telephone='20000000')
        self.paracetamol = Medicament.objects.create(
            nom='Paracétamol', unite='boîte', prix_unitaire=Decimal('500'))
        self.amoxicilline = Medicament.objects.create(
            nom='Amoxicilline', unite='boîte', prix_unitaire=Decimal('1200'))

        utilisateur = User.objects.create_user('pharma', password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur, role=Role.objects.get(code='pharmacien'))
        self.client.force_login(utilisateur)

    def commande_de_test(self):
        commande = Commande.objects.create(fournisseur=self.fournisseur,
                                           reference='BC-2026-001')
        LigneCommande.objects.create(commande=commande, medicament=self.paracetamol,
                                     quantite=100, prix_achat=Decimal('300'))
        LigneCommande.objects.create(commande=commande, medicament=self.amoxicilline,
                                     quantite=50, prix_achat=Decimal('800'))
        return commande

    # ── la commande ──────────────────────────────────────────────

    def test_le_montant_est_la_somme_des_lignes(self):
        commande = self.commande_de_test()

        # 100 × 300 + 50 × 800
        self.assertEqual(commande.montant_total(), Decimal('70000'))

    def test_passer_une_commande_depuis_le_formulaire(self):
        reponse = self.client.post(reverse('pharmacie:commande_ajouter'), {
            'fournisseur': self.fournisseur.pk,
            'reference': 'BC-2026-002',
            'statut': 'envoyee',
            'medicament_1': self.paracetamol.pk, 'quantite_1': '80', 'prix_achat_1': '300',
            'medicament_2': self.amoxicilline.pk, 'quantite_2': '20', 'prix_achat_2': '800',
            'medicament_3': '', 'quantite_3': '',     # ligne laissée vide
        })

        commande = Commande.objects.get(reference='BC-2026-002')
        self.assertEqual(commande.lignes.count(), 2)   # la ligne vide est ignorée
        self.assertEqual(commande.statut, 'envoyee')
        self.assertRedirects(
            reponse, reverse('pharmacie:commande_detail', args=[commande.pk]))

    def test_une_commande_sans_ligne_est_refusee(self):
        reponse = self.client.post(reverse('pharmacie:commande_ajouter'), {
            'fournisseur': self.fournisseur.pk, 'reference': 'VIDE', 'statut': 'brouillon',
        })

        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Commande.objects.filter(reference='VIDE').exists())

    # ── la réception ─────────────────────────────────────────────

    def test_receptionner_fait_entrer_la_marchandise_en_stock(self):
        commande = self.commande_de_test()
        peremption = timezone.localdate() + timedelta(days=500)

        ligne = commande.lignes.first()
        ligne.receptionner(100, numero_lot='PARA-A1', date_peremption=peremption)

        self.paracetamol.refresh_from_db()
        self.assertEqual(self.paracetamol.quantite_stock, 100)
        self.assertEqual(self.paracetamol.date_peremption, peremption)

        lot = Lot.objects.get(numero='PARA-A1')
        self.assertEqual(lot.quantite_restante, 100)
        self.assertEqual(lot.prix_achat, Decimal('300'))
        self.assertEqual(lot.fournisseur, self.fournisseur)

    def test_la_commande_passe_en_recue_quand_tout_est_arrive(self):
        commande = self.commande_de_test()

        self.client.post(
            reverse('pharmacie:commande_receptionner', args=[commande.pk]),
            {f'recu_{l.pk}': str(l.quantite) for l in commande.lignes.all()})

        commande.refresh_from_db()
        self.assertEqual(commande.statut, Commande.Statut.RECUE)
        self.assertEqual(commande.date_reception, timezone.localdate())

    def test_une_livraison_partielle_laisse_la_commande_ouverte(self):
        commande = self.commande_de_test()
        ligne = commande.lignes.first()

        self.client.post(
            reverse('pharmacie:commande_receptionner', args=[commande.pk]),
            {f'recu_{ligne.pk}': '40'})

        commande.refresh_from_db()
        ligne.refresh_from_db()
        self.assertEqual(ligne.quantite_recue, 40)
        self.assertEqual(ligne.quantite_restante(), 60)
        self.assertNotEqual(commande.statut, Commande.Statut.RECUE)

    def test_deux_livraisons_partielles_font_deux_lots(self):
        """Fidèle à la réalité : deux arrivages, deux péremptions possibles."""
        commande = self.commande_de_test()
        ligne = commande.lignes.first()

        ligne.receptionner(60, numero_lot='LOT-A',
                           date_peremption=timezone.localdate() + timedelta(days=200))
        ligne.receptionner(40, numero_lot='LOT-B',
                           date_peremption=timezone.localdate() + timedelta(days=900))

        self.assertEqual(Lot.objects.filter(medicament=self.paracetamol).count(), 2)
        self.paracetamol.refresh_from_db()
        self.assertEqual(self.paracetamol.quantite_stock, 100)
        # La péremption retenue est la plus proche des deux.
        self.assertEqual(self.paracetamol.date_peremption,
                         timezone.localdate() + timedelta(days=200))

    def test_on_ne_peut_pas_recevoir_plus_que_commande(self):
        commande = self.commande_de_test()
        ligne = commande.lignes.first()   # 100 commandés

        with self.assertRaises(ValueError):
            ligne.receptionner(150)

        self.paracetamol.refresh_from_db()
        self.assertEqual(self.paracetamol.quantite_stock, 0)

    def test_une_reception_vide_ne_change_rien(self):
        commande = self.commande_de_test()

        reponse = self.client.post(
            reverse('pharmacie:commande_receptionner', args=[commande.pk]),
            {f'recu_{l.pk}': '0' for l in commande.lignes.all()})

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(MouvementStock.objects.count(), 0)
        commande.refresh_from_db()
        self.assertEqual(commande.statut, Commande.Statut.BROUILLON)

    # ── le circuit complet ───────────────────────────────────────

    def test_de_la_commande_a_la_dispensation(self):
        """Commander, recevoir, servir : le stock doit suivre de bout en bout."""
        commande = self.commande_de_test()
        ligne = commande.lignes.first()
        ligne.receptionner(100, numero_lot='PARA-A1',
                           date_peremption=timezone.localdate() + timedelta(days=400))

        MouvementStock.objects.create(medicament=self.paracetamol,
                                      type_mouvement='sortie', quantite=12)

        self.paracetamol.refresh_from_db()
        self.assertEqual(self.paracetamol.quantite_stock, 88)
        self.assertEqual(self.paracetamol.stock_par_lots(), 88)
        self.assertEqual(Lot.objects.get(numero='PARA-A1').quantite_restante, 88)


@override_settings(ALLOWED_HOSTS=['testserver'])
class FournisseurTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        utilisateur = User.objects.create_user('pharma', password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur, role=Role.objects.get(code='pharmacien'))
        self.client.force_login(utilisateur)

    def test_ajouter_un_fournisseur(self):
        reponse = self.client.post(reverse('pharmacie:fournisseur_ajouter'), {
            'nom': 'Laborex Mali', 'contact': 'M. Diallo',
            'telephone': '20112233', 'actif': 'on',
        })

        self.assertRedirects(reponse, reverse('pharmacie:fournisseurs'))
        self.assertTrue(Fournisseur.objects.filter(nom='Laborex Mali').exists())

    def test_un_fournisseur_sans_nom_est_refuse(self):
        reponse = self.client.post(reverse('pharmacie:fournisseur_ajouter'),
                                   {'nom': '   '})

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(Fournisseur.objects.count(), 0)

    def test_la_liste_saffiche(self):
        Fournisseur.objects.create(nom='Pharmadis Bamako')

        reponse = self.client.get(reverse('pharmacie:fournisseurs'))

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Pharmadis Bamako')
