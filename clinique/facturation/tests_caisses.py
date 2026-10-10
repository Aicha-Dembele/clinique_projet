"""Tests des deux caisses : la pharmacie et la réception.

Règle visée (voir facturation/regles.py, « Qui encaisse quoi ») : les
médicaments se règlent au comptoir de la pharmacie, chez le pharmacien qui
vient de les servir. La consultation, l'examen et l'hospitalisation se
règlent à la réception. Ni l'un ni l'autre ne peut encaisser la caisse du
voisin.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Consultation, Ordonnance, Rendez_vous
from facturation.models import Facture, Paiement, Tarif
from facturation.regles import (
    CAISSE_PHARMACIE, CAISSE_RECEPTION, blocage_caisse, caisse_de, facturer)
from patients.models import Patient
from personnel.models import Medecin
from pharmacie.models import Medicament, MouvementStock


@override_settings(ALLOWED_HOSTS=['testserver'])
class DeuxCaissesTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        Tarif.objects.create(type_service='consultation', specialite='Généraliste',
                             nom='Consultation généraliste', prix=Decimal('3000'))
        self.medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Diag',
            specialite='Généraliste', role='medecin')
        self.patient = Patient.objects.create(
            nom='Traore', prenom='Awa', sexe='Féminin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='0000', email='a@b.c', numero_urgence='0000')

        # Une facture de soins (consultation) et une facture de médicaments.
        rdv = Rendez_vous.objects.create(
            patient=self.patient, medecin=self.medecin, date='2026-12-01T09:00')
        self.facture_soins = facturer(self.patient, 'rendez_vous', rdv)

        consultation = Consultation.objects.create(
            rendez_vous=rdv, motif='Fièvre', diagnostic='Paludisme')
        self.ordonnance = Ordonnance.objects.create(
            consultation=consultation, date=date(2026, 12, 1),
            medicaments='Artémether 20 mg')
        # Le montant d'une facture pharmacie vient des SORTIES de stock
        # rattachées à l'ordonnance : sans sortie, elle retombe à 0 et passe
        # pour réglée. On sert donc vraiment le médicament.
        medicament = Medicament.objects.create(
            nom='Artémether', prix_unitaire=Decimal('1500'))
        # Le stock ne bouge que par des mouvements : on approvisionne avant
        # de servir, sinon la sortie ferait passer le stock sous zéro.
        MouvementStock.objects.create(
            medicament=medicament, type_mouvement='entree', quantite=10,
            prix_unitaire=Decimal('1500'))
        self.facture_medicaments = Facture.objects.create(
            patient=self.patient, ordonnance=self.ordonnance)
        MouvementStock.objects.create(
            medicament=medicament, type_mouvement='sortie', quantite=3,
            prix_unitaire=Decimal('1500'), ordonnance=self.ordonnance,
            patient=self.patient)
        self.facture_medicaments.save()     # recalcule : 3 × 1 500 = 4 500
        self.facture_medicaments.refresh_from_db()

    def connecter(self, code_role, identifiant):
        utilisateur = User.objects.create_user(identifiant, password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur, role=Role.objects.get(code=code_role))
        self.client.force_login(utilisateur)
        return utilisateur

    # ── la règle elle-même ───────────────────────────────────────

    def test_une_facture_de_medicaments_se_regle_a_la_pharmacie(self):
        self.assertEqual(caisse_de(self.facture_medicaments), CAISSE_PHARMACIE)

    def test_une_facture_de_soins_se_regle_a_la_reception(self):
        self.assertEqual(caisse_de(self.facture_soins), CAISSE_RECEPTION)

    def test_le_pharmacien_ne_peut_pas_encaisser_une_consultation(self):
        refus = blocage_caisse(self.facture_soins, 'pharmacien')

        self.assertIsNotNone(refus)
        self.assertIn('réception', refus)

    def test_la_receptionniste_ne_peut_pas_encaisser_des_medicaments(self):
        refus = blocage_caisse(self.facture_medicaments, 'receptionniste')

        self.assertIsNotNone(refus)
        self.assertIn('pharmacie', refus)

    def test_chacun_encaisse_sa_propre_caisse(self):
        self.assertIsNone(blocage_caisse(self.facture_medicaments, 'pharmacien'))
        self.assertIsNone(blocage_caisse(self.facture_soins, 'receptionniste'))

    def test_ladministrateur_tient_les_deux_caisses(self):
        self.assertIsNone(blocage_caisse(self.facture_medicaments, 'admin'))
        self.assertIsNone(blocage_caisse(self.facture_soins, 'admin'))

    def test_un_medecin_ne_tient_aucune_caisse(self):
        self.assertIsNotNone(blocage_caisse(self.facture_soins, 'medecin'))
        self.assertIsNotNone(blocage_caisse(self.facture_medicaments, 'medecin'))

    # ── ce que le serveur refuse réellement ──────────────────────

    def test_le_pharmacien_encaisse_les_medicaments(self):
        self.connecter('pharmacien', 'pharma')

        self.client.post(reverse('facturation:paiement_ajouter'), {
            'facture': self.facture_medicaments.pk, 'montant': '4500',
            'mode_paiement': 'cash', 'note': '',
        })

        self.assertEqual(Paiement.objects.count(), 1)
        self.facture_medicaments.refresh_from_db()
        self.assertEqual(self.facture_medicaments.statut, 'payé')

    def test_le_pharmacien_est_refuse_sur_une_consultation_meme_en_forcant(self):
        """Le menu ne la propose pas ; on vérifie que le serveur refuse aussi."""
        self.connecter('pharmacien', 'pharma')

        self.client.post(reverse('facturation:paiement_ajouter'), {
            'facture': self.facture_soins.pk, 'montant': '3000',
            'mode_paiement': 'cash', 'note': '',
        })

        self.assertEqual(Paiement.objects.count(), 0)
        self.facture_soins.refresh_from_db()
        self.assertEqual(self.facture_soins.statut, 'non payé')

    def test_la_receptionniste_est_refusee_sur_des_medicaments(self):
        self.connecter('receptionniste', 'recept')

        self.client.post(reverse('facturation:paiement_ajouter'), {
            'facture': self.facture_medicaments.pk, 'montant': '4500',
            'mode_paiement': 'cash', 'note': '',
        })

        self.assertEqual(Paiement.objects.count(), 0)

    # ── ce que chacun voit ───────────────────────────────────────

    def test_le_menu_du_pharmacien_ne_montre_que_les_ordonnances(self):
        self.connecter('pharmacien', 'pharma')

        reponse = self.client.get(reverse('facturation:paiement_ajouter'))

        factures = list(reponse.context['factures'])
        self.assertIn(self.facture_medicaments, factures)
        self.assertNotIn(self.facture_soins, factures)

    def test_le_menu_de_la_reception_ne_montre_pas_les_ordonnances(self):
        self.connecter('receptionniste', 'recept')

        reponse = self.client.get(reverse('facturation:paiement_ajouter'))

        factures = list(reponse.context['factures'])
        self.assertIn(self.facture_soins, factures)
        self.assertNotIn(self.facture_medicaments, factures)

    def test_chacun_ne_voit_que_les_encaissements_de_sa_caisse(self):
        Paiement.objects.create(facture=self.facture_soins,
                                montant=Decimal('3000'), mode_paiement='cash')
        Paiement.objects.create(facture=self.facture_medicaments,
                                montant=Decimal('4500'), mode_paiement='cash')

        self.connecter('pharmacien', 'pharma')
        vus = list(self.client.get(reverse('facturation:paiements')).context['paiements'])
        self.assertEqual([p.facture_id for p in vus], [self.facture_medicaments.pk])

        self.connecter('receptionniste', 'recept')
        vus = list(self.client.get(reverse('facturation:paiements')).context['paiements'])
        self.assertEqual([p.facture_id for p in vus], [self.facture_soins.pk])

    def test_le_pharmacien_repart_avec_le_recu(self):
        self.connecter('pharmacien', 'pharma')

        reponse = self.client.post(reverse('facturation:paiement_ajouter'), {
            'facture': self.facture_medicaments.pk, 'montant': '4500',
            'mode_paiement': 'cash', 'note': '',
        })

        paiement = Paiement.objects.get()
        self.assertRedirects(
            reponse, reverse('facturation:paiement_recu', args=[paiement.pk]))
