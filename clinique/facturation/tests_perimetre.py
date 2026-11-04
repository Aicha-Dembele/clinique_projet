"""Ce que chaque caisse VOIT de la facturation.

Règle (facturation/regles.py, « Ce que chaque rôle VOIT ») :
  - le pharmacien : les factures d'ordonnance, leurs paiements et la part de
    l'assurance sur les médicaments, qu'il réclame lui-même ;
  - la réceptionniste : les consultations, examens et hospitalisations.
Ni l'un ni l'autre ne voit l'autre caisse — même en tapant l'adresse d'une
facture à la main.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Consultation, Ordonnance, Rendez_vous
from facturation.models import Assurance, Facture, Paiement, Tarif
from facturation.regles import facturer
from patients.models import Patient
from personnel.models import Medecin
from pharmacie.models import Medicament, MouvementStock


@override_settings(ALLOWED_HOSTS=['testserver'])
class PerimetrePharmacienTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        Tarif.objects.create(type_service='consultation', specialite='Généraliste',
                             nom='Consultation généraliste', prix=Decimal('3000'))
        assurance = Assurance.objects.create(nom='Mutuelle de test',
                                             taux_prise_en_charge=Decimal('70'))
        medecin = Medecin.objects.create(nom='House', prenom='G', telephone='1', service='Diag',
                                         specialite='Généraliste', role='medecin')
        patient = Patient.objects.create(
            nom='Traore', prenom='Awa', sexe='Féminin', date_naissance=date(1990, 1, 1),
            adresse='Bamako', telephone='0000', email='a@b.c', numero_urgence='0000',
            assurance=assurance)

        # Une facture de soins (consultation) et une facture de médicaments,
        # toutes deux prises en charge par l'assurance.
        rdv = Rendez_vous.objects.create(patient=patient, medecin=medecin, date='2026-12-01T09:00')
        self.soins = facturer(patient, 'rendez_vous', rdv)
        self.paiement_soins = Paiement.objects.create(
            facture=self.soins, montant=self.soins.part_patient(), mode_paiement='cash')

        consultation = Consultation.objects.create(rendez_vous=rdv, motif='Fièvre', diagnostic='Paludisme')
        ordonnance = Ordonnance.objects.create(consultation=consultation, date=date(2026, 12, 1),
                                               medicaments='Artémether 20 mg')
        medicament = Medicament.objects.create(nom='Artémether', prix_unitaire=Decimal('1500'))
        MouvementStock.objects.create(medicament=medicament, type_mouvement='entree', quantite=10,
                                      prix_unitaire=Decimal('1500'))
        self.medicaments = Facture.objects.create(patient=patient, ordonnance=ordonnance, assurance=assurance)
        MouvementStock.objects.create(medicament=medicament, type_mouvement='sortie', quantite=3,
                                      prix_unitaire=Decimal('1500'), ordonnance=ordonnance, patient=patient)
        self.medicaments.save()
        self.paiement_medicaments = Paiement.objects.create(
            facture=self.medicaments, montant=Decimal('500'), mode_paiement='cash')

    def connecter(self, code_role):
        u = User.objects.create_user(code_role, password='motdepasse-de-test')
        Profil.objects.create(user=u, role=Role.objects.get(code=code_role))
        self.client.force_login(u)

    # ── le pharmacien ────────────────────────────────────────────

    def test_la_liste_des_factures_ne_montre_que_les_medicaments(self):
        self.connecter('pharmacien')
        r = self.client.get(reverse('facturation:liste'))
        self.assertEqual([f.pk for f in r.context['factures']], [self.medicaments.pk])
        self.assertEqual(r.context['total_factures'], 1)

    def test_une_facture_de_soins_ne_souvre_pas_meme_par_son_adresse(self):
        self.connecter('pharmacien')
        for nom in ('facturation:detail', 'facturation:facture_pdf'):
            with self.subTest(page=nom):
                self.assertEqual(self.client.get(reverse(nom, args=[self.soins.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('facturation:detail', args=[self.medicaments.pk])).status_code, 200)

    def test_le_recu_dune_consultation_ne_souvre_pas(self):
        self.connecter('pharmacien')
        for nom in ('facturation:paiement_recu', 'facturation:paiement_pdf'):
            with self.subTest(page=nom):
                self.assertEqual(self.client.get(reverse(nom, args=[self.paiement_soins.pk])).status_code, 404)
        self.assertEqual(
            self.client.get(reverse('facturation:paiement_recu', args=[self.paiement_medicaments.pk])).status_code, 200)

    def test_les_paiements_ne_montrent_que_la_pharmacie(self):
        self.connecter('pharmacien')
        r = self.client.get(reverse('facturation:paiements'))
        self.assertEqual([p.pk for p in r.context['paiements']], [self.paiement_medicaments.pk])

    def test_les_creances_ne_montrent_que_la_part_assurance_des_ordonnances(self):
        self.connecter('pharmacien')
        r = self.client.get(reverse('facturation:creances'))
        vues = [f.pk for g in r.context['groupes'] for f in g['factures']]
        self.assertEqual(vues, [self.medicaments.pk])

    def marquer(self, facture, action='reclame'):
        return self.client.post(reverse('facturation:creances_marquer'),
                                {'facture': facture.pk, 'action': action})

    def test_le_pharmacien_reclame_la_part_assurance_des_medicaments(self):
        self.connecter('pharmacien')
        self.assertContains(self.client.get(reverse('facturation:creances')),
                            reverse('facturation:creances_marquer'))
        self.marquer(self.medicaments)
        self.medicaments.refresh_from_db()
        self.assertEqual(self.medicaments.statut_assurance, 'reclame')

    def test_le_pharmacien_ne_peut_pas_marquer_une_consultation(self):
        self.connecter('pharmacien')
        self.marquer(self.soins)
        self.soins.refresh_from_db()
        self.assertEqual(self.soins.statut_assurance, 'a_reclamer')

    def test_lexport_ne_contient_que_les_medicaments(self):
        self.connecter('pharmacien')
        contenu = self.client.get(reverse('facturation:factures_export')).content.decode('utf-8-sig')
        self.assertIn(f'FAC-{self.medicaments.pk:04d}', contenu)
        self.assertNotIn(f'FAC-{self.soins.pk:04d}', contenu)

    # ── la réceptionniste : les soins, pas la pharmacie ──────────

    def test_la_reception_ne_voit_que_les_soins(self):
        self.connecter('receptionniste')
        r = self.client.get(reverse('facturation:liste'))
        self.assertEqual([f.pk for f in r.context['factures']], [self.soins.pk])
        r = self.client.get(reverse('facturation:creances'))
        self.assertEqual([f.pk for g in r.context['groupes'] for f in g['factures']], [self.soins.pk])
        r = self.client.get(reverse('facturation:paiements'))
        self.assertEqual([p.pk for p in r.context['paiements']], [self.paiement_soins.pk])

    def test_la_reception_ne_touche_pas_une_facture_de_medicaments(self):
        self.connecter('receptionniste')
        for nom in ('facturation:detail', 'facturation:modifier', 'facturation:supprimer',
                    'facturation:recalculer'):
            with self.subTest(page=nom):
                self.assertEqual(self.client.get(reverse(nom, args=[self.medicaments.pk])).status_code, 404)
        for nom in ('facturation:paiement_modifier', 'facturation:paiement_supprimer'):
            with self.subTest(page=nom):
                self.assertEqual(
                    self.client.get(reverse(nom, args=[self.paiement_medicaments.pk])).status_code, 404)
        self.marquer(self.medicaments)
        self.medicaments.refresh_from_db()
        self.assertEqual(self.medicaments.statut_assurance, 'a_reclamer')

    def test_la_reception_ne_facture_pas_les_medicaments_a_la_main(self):
        self.connecter('receptionniste')
        r = self.client.get(reverse('facturation:ajouter'))
        self.assertNotIn('ordonnance', [s['code'] for s in r.context['services']])
        avant = Facture.objects.count()
        self.client.post(reverse('facturation:ajouter'), {
            'patient': self.medicaments.patient_id, 'service': 'ordonnance',
            'ordonnance': self.medicaments.ordonnance_id})
        self.assertEqual(Facture.objects.count(), avant)

    # ── l'administrateur voit tout ───────────────────────────────

    def test_ladministrateur_voit_toujours_tout(self):
        self.connecter('admin')
        r = self.client.get(reverse('facturation:liste'))
        self.assertEqual({f.pk for f in r.context['factures']}, {self.soins.pk, self.medicaments.pk})
