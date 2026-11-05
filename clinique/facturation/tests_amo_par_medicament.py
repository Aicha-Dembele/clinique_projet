"""L'AMO se calcule médicament par médicament, et sa part se réclame à la fin du mois.

Son exemple : Doliprane 1 000 F, Efferalgan 1 500 F, un troisième à 1 200 F. Le patient
paie 30 % de chacun, soit 300 + 450 + 360 = 1 110 F. Les 70 % restent à réclamer à l'AMO,
soit 700 + 1 050 + 840 = 2 590 F.
"""
import importlib
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.apps import apps
from django.contrib.messages import get_messages
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.roles import installer_roles
from consultation.models import Consultation, Ordonnance, Rendez_vous
from facturation.models import Assurance, Facture, LigneFacture, Paiement
from facturation.tests_amo import creer_patient, creer_utilisateur
from personnel.models import Medecin
from pharmacie.models import Medicament, MouvementStock
from pharmacie.ventes import a_reclamer_par_assurance


@override_settings(ALLOWED_HOSTS=['testserver'])
class Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        self.amo, _ = Assurance.objects.get_or_create(
            nom='AMO', defaults={'taux_prise_en_charge': Decimal('70')})
        self.client.force_login(creer_utilisateur('pharma', 'pharmacien'))
        self.patient = creer_patient(self.amo, numero_assure='AMO-1')
        self.ordo = self.ordonnance(self.patient)

    def medicament(self, nom, prix, rembourse=True):
        medicament = Medicament.objects.create(nom=nom, prix_unitaire=Decimal(prix), rembourse=rembourse)
        MouvementStock.objects.create(medicament=medicament, type_mouvement='entree', quantite=50,
                                      prix_unitaire=Decimal(prix))
        return medicament

    def ordonnance(self, patient):
        medecin = Medecin.objects.create(nom='House', prenom='G', telephone='1', service='Diag',
                                         specialite='Généraliste', role='medecin')
        rdv = Rendez_vous.objects.create(patient=patient, medecin=medecin, date='2026-12-01T09:00')
        consultation = Consultation.objects.create(rendez_vous=rdv, motif='Fièvre', diagnostic='Paludisme')
        return Ordonnance.objects.create(consultation=consultation, date=date(2026, 12, 1),
                                         medicaments='- Doliprane Test : 1 matin')

    def servir(self, *medicaments, quantite=1, patient=None, ordonnance=None):
        return self.client.post(reverse('pharmacie:sortie_stock'), {
            'patient': (patient or self.patient).pk, 'ordonnance': (ordonnance or self.ordo).pk,
            'ligne_med': [m.pk for m in medicaments], 'ligne_qte': [quantite] * len(medicaments)})

    def facture(self, ordonnance=None):
        return Facture.objects.get(ordonnance=ordonnance or self.ordo)

    def servir_son_exemple(self):
        self.servir(self.medicament('Doliprane Test', '1000'),
                    self.medicament('Efferalgan Test', '1500'),
                    self.medicament('Troisieme Test', '1200'))
        return self.facture()


class CalculParMedicamentTests(Base):

    def test_chaque_medicament_a_sa_part_enregistree(self):
        facture = self.servir_son_exemple()
        parts = {l.designation(): (l.part_assurance, l.part_patient)
                 for l in LigneFacture.objects.filter(facture=facture)}

        self.assertEqual(parts['Doliprane Test'], (Decimal('700'), Decimal('300')))
        self.assertEqual(parts['Efferalgan Test'], (Decimal('1050'), Decimal('450')))
        self.assertEqual(parts['Troisieme Test'], (Decimal('840'), Decimal('360')))

    def test_le_patient_paie_la_somme_de_ses_parts(self):
        facture = self.servir_son_exemple()

        self.assertEqual(facture.montant_total, Decimal('3700'))
        self.assertEqual(facture.part_patient(), Decimal('1110'))
        self.assertEqual(facture.montant_restant(), Decimal('1110'))

    def test_la_part_de_lamo_est_enregistree_sur_la_facture(self):
        facture = self.servir_son_exemple()

        self.assertEqual(facture.montant_assurance, Decimal('2590'))
        self.assertEqual(facture.part_assurance(), Decimal('2590'))

    def test_on_additionne_au_lieu_de_calculer_sur_le_total(self):
        # 70 % de 1 001 F = 700,70 F, arrondis à 701 F par médicament : 3 × 701 = 2 103 F.
        # Calculé sur le total, 70 % de 3 003 F aurait donné 2 102 F.
        self.servir(self.medicament('Un Test', '1001'), self.medicament('Deux Test', '1001'),
                    self.medicament('Trois Test', '1001'))
        facture = self.facture()

        self.assertEqual(facture.part_assurance(), Decimal('2103'))
        self.assertEqual(facture.part_patient(), Decimal('900'))

    def test_les_deux_parts_redonnent_toujours_le_prix(self):
        self.servir(self.medicament('Un Test', '1175'), self.medicament('Deux Test', '333'))
        for ligne in self.facture().lignes.all():
            self.assertEqual(ligne.part_assurance + ligne.part_patient, ligne.sous_total())
        facture = self.facture()
        self.assertEqual(facture.part_assurance() + facture.part_patient(), facture.montant_total)

    def test_la_quantite_compte_dans_le_calcul_du_medicament(self):
        self.servir(self.medicament('Doliprane Test', '1000'), quantite=2)
        ligne = self.facture().lignes.get()

        self.assertEqual((ligne.part_assurance, ligne.part_patient), (Decimal('1400'), Decimal('600')))

    def test_un_medicament_non_couvert_reste_entierement_au_patient(self):
        self.servir(self.medicament('Doliprane Test', '1000'),
                    self.medicament('Efferalgan Test', '1500', rembourse=False))
        facture = self.facture()

        self.assertEqual(facture.part_assurance(), Decimal('700'))
        self.assertEqual(facture.part_patient(), Decimal('1800'))    # 300 + 1 500

    def test_sans_assurance_le_patient_paie_tout(self):
        patient = creer_patient()
        ordonnance = self.ordonnance(patient)
        self.servir(self.medicament('Doliprane Test', '1000'), patient=patient, ordonnance=ordonnance)
        facture = self.facture(ordonnance)

        self.assertEqual(facture.part_assurance(), Decimal('0'))
        self.assertEqual(facture.part_patient(), Decimal('1000'))
        self.assertEqual(facture.lignes.get().part_patient, Decimal('1000'))

    def test_un_second_passage_ajoute_sa_part_sans_toucher_aux_autres(self):
        self.servir(self.medicament('Doliprane Test', '1000'))
        self.servir(self.medicament('Efferalgan Test', '1500'))
        facture = self.facture()

        self.assertEqual(facture.lignes.count(), 2)
        self.assertEqual(facture.part_assurance(), Decimal('1750'))
        self.assertEqual(facture.part_patient(), Decimal('750'))

    def test_regler_la_part_du_patient_solde_la_facture_et_laisse_lamo_a_reclamer(self):
        facture = self.servir_son_exemple()
        Paiement.objects.create(facture=facture, montant=Decimal('1110'), mode_paiement='cash')
        facture.refresh_from_db()

        self.assertEqual(facture.statut, 'payé')
        self.assertEqual(facture.statut_assurance, 'a_reclamer')
        self.assertEqual(facture.part_assurance(), Decimal('2590'))

    def test_le_message_de_vente_annonce_les_sommes_additionnees(self):
        reponse = self.servir(self.medicament('Doliprane Test', '1000'),
                              self.medicament('Efferalgan Test', '1500'),
                              self.medicament('Troisieme Test', '1200'))
        textes = [str(m) for m in get_messages(reponse.wsgi_request)]

        self.assertTrue(any('Part AMO : 2 590' in t and '1 110' in t for t in textes), textes)


class AffichageTests(Base):

    def test_la_facture_montre_la_part_de_chaque_medicament(self):
        facture = self.servir_son_exemple()
        reponse = self.client.get(reverse('facturation:detail', args=[facture.pk]))

        self.assertContains(reponse, 'AMO 700 FCFA · Patient 300 FCFA')
        self.assertContains(reponse, 'AMO 1050 FCFA · Patient 450 FCFA')
        self.assertContains(reponse, 'AMO 840 FCFA · Patient 360 FCFA')

    def test_le_recu_montre_ce_que_le_patient_paie_par_medicament(self):
        facture = self.servir_son_exemple()
        paiement = Paiement.objects.create(facture=facture, montant=Decimal('1110'), mode_paiement='cash')
        reponse = self.client.get(reverse('facturation:paiement_recu', args=[paiement.pk]))

        self.assertContains(reponse, 'Doliprane Test')
        self.assertContains(reponse, '<td>300</td>', html=True)
        self.assertContains(reponse, '<td>1050</td>', html=True)

    def test_les_pdf_se_generent_avec_le_detail(self):
        facture = self.servir_son_exemple()
        paiement = Paiement.objects.create(facture=facture, montant=Decimal('1110'), mode_paiement='cash')

        for adresse in (reverse('facturation:facture_pdf', args=[facture.pk]),
                        reverse('facturation:paiement_pdf', args=[paiement.pk])):
            reponse = self.client.get(adresse)
            self.assertEqual(reponse.status_code, 200)
            self.assertTrue(reponse.content.startswith(b'%PDF'))

    def test_lecran_de_vente_prepare_la_part_de_chaque_ligne(self):
        reponse = self.client.get(reverse('pharmacie:sortie_stock'))

        self.assertContains(reponse, 'class="ol-parts"')
        self.assertContains(reponse, 'de chaque médicament couvert')


class ReclamationTests(Base):

    def page(self, **filtres):
        return self.client.get(reverse('facturation:creances'), filtres)

    def test_le_pharmacien_trouve_le_detail_par_medicament(self):
        self.servir_son_exemple()
        reponse = self.page()

        self.assertContains(reponse, 'Doliprane Test')
        self.assertContains(reponse, 'Efferalgan Test')
        self.assertContains(reponse, '<span class="medic-part">1050</span>', html=True)
        self.assertEqual(reponse.context['total_a_reclamer'], Decimal('2590'))
        self.assertEqual(reponse.context['montant_a_reclamer'], Decimal('2590'))

    def test_la_page_porte_un_nom_clair_pour_le_pharmacien(self):
        self.assertContains(self.page(), "À réclamer à l'AMO")

    def test_ladministrateur_garde_le_nom_habituel(self):
        self.client.force_login(creer_utilisateur('chef', 'admin'))
        reponse = self.page()

        self.assertContains(reponse, 'Créances assurances')
        self.assertNotContains(reponse, "À réclamer à l'AMO")

    def test_le_fichier_a_une_ligne_par_medicament_et_un_total(self):
        facture = self.servir_son_exemple()
        contenu = (self.client.get(reverse('facturation:creances_export'), {'assurance': self.amo.pk})
                   .content.decode('utf-8-sig'))
        lignes = [l.split(';') for l in contenu.strip().splitlines()]

        self.assertEqual(len(lignes), 5)    # les titres, 3 médicaments, le total
        titres = lignes[0]
        a_reclamer = titres.index('A reclamer')
        par_nom = {l[titres.index('Prestation')]: l for l in lignes[1:4]}
        self.assertEqual(par_nom['Doliprane Test'][a_reclamer], '700')
        self.assertEqual(par_nom['Efferalgan Test'][a_reclamer], '1050')
        self.assertEqual(par_nom['Troisieme Test'][a_reclamer], '840')
        self.assertEqual(par_nom['Doliprane Test'][titres.index('Facture')], f'FAC-{facture.pk:04d}')
        self.assertEqual(par_nom['Doliprane Test'][titres.index('Numero assure')], 'AMO-1')
        self.assertEqual(lignes[4][0], 'TOTAL')
        self.assertEqual(lignes[4][a_reclamer], '2590')
        self.assertEqual(lignes[4][titres.index('Part patient')], '1110')

    def test_une_ancienne_facture_sans_ligne_reste_dans_le_fichier(self):
        ancienne = Facture.objects.create(patient=self.patient, assurance=self.amo)
        Facture.objects.filter(pk=ancienne.pk).update(
            ordonnance=self.ordo, montant_total=Decimal('1000'), montant_remboursable=Decimal('1000'),
            montant_assurance=None)
        contenu = (self.client.get(reverse('facturation:creances_export'))
                   .content.decode('utf-8-sig'))

        self.assertIn(f'FAC-{ancienne.pk:04d}', contenu)
        self.assertIn(';1000;700;300;', contenu)

    def test_reclamer_le_mois_garde_les_montants_et_vide_le_rappel(self):
        facture = self.servir_son_exemple()
        self.assertEqual(a_reclamer_par_assurance(), [{'nom': 'AMO', 'montant': Decimal('2590')}])

        self.client.post(reverse('facturation:creances_marquer'),
                         {'facture': facture.pk, 'action': 'reclame'})
        facture.refresh_from_db()

        self.assertEqual(facture.statut_assurance, 'reclame')
        self.assertEqual(facture.part_assurance(), Decimal('2590'))
        self.assertEqual(a_reclamer_par_assurance(), [])
        self.assertEqual(self.page().context['montant_reclame'], Decimal('2590'))

    def test_les_ventes_et_le_tableau_de_bord_rappellent_la_somme(self):
        self.servir_son_exemple()
        for adresse in (reverse('pharmacie:ventes'), reverse('dashboard')):
            reponse = self.client.get(adresse)
            self.assertContains(reponse, 'Part des assurances à réclamer')
            self.assertContains(reponse, 'AMO <strong>2 590 FCFA</strong>')

    def test_pas_de_rappel_quand_il_ny_a_rien_a_reclamer(self):
        self.assertNotContains(self.client.get(reverse('pharmacie:ventes')),
                               'Voir le détail')

    def test_un_ajout_sur_une_ordonnance_deja_reclamee_est_signale(self):
        self.servir(self.medicament('Doliprane Test', '1000'))
        self.client.post(reverse('facturation:creances_marquer'),
                         {'facture': self.facture().pk, 'action': 'reclame'})

        reponse = self.servir(self.medicament('Efferalgan Test', '1500'))
        textes = [str(m) for m in get_messages(reponse.wsgi_request)]

        self.assertTrue(any('déjà été réclamée' in t and '1 050' in t for t in textes), textes)

    def test_un_ajout_avant_la_reclamation_ne_signale_rien(self):
        self.servir(self.medicament('Doliprane Test', '1000'))
        reponse = self.servir(self.medicament('Efferalgan Test', '1500'))
        textes = [str(m) for m in get_messages(reponse.wsgi_request)]

        self.assertFalse(any('déjà été réclamée' in t for t in textes), textes)


class FacturesDejaEnregistreesTests(Base):
    """Les factures établies avant ce calcul reçoivent leurs parts à la mise à jour."""

    def executer(self):
        module = importlib.import_module('facturation.migrations.0023_parts_par_ligne')
        module.partager_les_lignes_existantes(apps, SimpleNamespace(connection=connection))

    def test_les_lignes_existantes_recoivent_leurs_parts(self):
        facture = self.servir_son_exemple()
        LigneFacture.objects.filter(facture=facture).update(part_assurance=0, part_patient=0)
        Facture.objects.filter(pk=facture.pk).update(montant_assurance=None)

        self.executer()
        facture.refresh_from_db()

        self.assertEqual(facture.montant_assurance, Decimal('2590'))
        parts = sorted(l.part_patient for l in facture.lignes.all())
        self.assertEqual(parts, [Decimal('300'), Decimal('360'), Decimal('450')])

    def test_une_facture_sans_ligne_garde_son_ancien_calcul(self):
        ancienne = Facture.objects.create(patient=self.patient, assurance=self.amo)
        Facture.objects.filter(pk=ancienne.pk).update(
            montant_total=Decimal('1000'), montant_remboursable=Decimal('1000'), montant_assurance=None)

        self.executer()
        ancienne.refresh_from_db()

        self.assertIsNone(ancienne.montant_assurance)
        self.assertEqual(ancienne.part_assurance(), Decimal('700'))
        self.assertEqual(ancienne.part_patient(), Decimal('300'))

    def test_une_facture_sans_assurance_ne_doit_rien_a_personne(self):
        facture = Facture.objects.create(patient=creer_patient())
        LigneFacture.objects.create(facture=facture, description='Consultation', type_service='consultation',
                                    prix_unitaire=Decimal('5000'), quantite=1)

        self.executer()
        ligne = facture.lignes.get()

        self.assertEqual(ligne.part_assurance, Decimal('0'))
        self.assertEqual(ligne.part_patient, Decimal('5000'))


class RappelParAssuranceTests(Base):

    def test_une_ancienne_assurance_nest_pas_comptee_comme_lamo(self):
        self.servir_son_exemple()
        takaful = Assurance.objects.create(nom='Takaful 100%', taux_prise_en_charge=Decimal('100'), actif=False)
        patient = creer_patient(takaful)
        ordonnance = self.ordonnance(patient)
        self.servir(self.medicament('Ancien Test', '3000'), patient=patient, ordonnance=ordonnance)

        self.assertEqual(a_reclamer_par_assurance(), [
            {'nom': 'Takaful 100%', 'montant': Decimal('3000')},
            {'nom': 'AMO', 'montant': Decimal('2590')},
        ])
