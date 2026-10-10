"""Tests de l'application de l'assurance.

Deux règles :

1. **Un service, un calcul.** La consultation, l'examen et l'hospitalisation
   sont facturés séparément ; l'assurance s'applique sur chacun à part et les
   montants ne s'additionnent jamais. Chaque facture a son reçu.

2. **Sur une ordonnance, médicament par médicament.** Un médicament non
   remboursé reste entièrement à la charge du patient, pendant que les autres
   sont pris en charge normalement.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings

from consultation.models import (
    Consultation, ExamenMedical, Hospitalisation, Ordonnance, Rendez_vous)
from facturation.models import Assurance, Facture, Paiement, Tarif
from facturation.regles import facturer
from patients.models import Patient
from personnel.models import Medecin
from pharmacie.models import Medicament, MouvementStock


@override_settings(ALLOWED_HOSTS=['testserver'])
class AssuranceParServiceTests(TestCase):
    """Chaque service est calculé à part, jamais en bloc."""

    def setUp(self):
        self.assurance = Assurance.objects.create(
            nom='Mutuelle de test', taux_prise_en_charge=Decimal('70'))
        self.patient = Patient.objects.create(
            nom='Traore', prenom='Awa', sexe='Féminin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='0000', email='a@b.c', numero_urgence='0000',
            assurance=self.assurance)
        self.medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Diag',
            specialite='Généraliste', role='medecin')

        Tarif.objects.create(type_service='consultation', specialite='Généraliste',
                             nom='Consultation', prix=Decimal('10000'))
        Tarif.objects.create(type_service='examen', specialite='Radiographie',
                             nom='Radiographie', prix=Decimal('5000'))
        Tarif.objects.create(type_service='hospitalisation', specialite='Standard',
                             nom='Chambre standard', prix=Decimal('15000'))

        self.rdv = Rendez_vous.objects.create(
            patient=self.patient, medecin=self.medecin, date='2026-12-01T09:00')
        self.consultation = Consultation.objects.create(
            rendez_vous=self.rdv, motif='Fièvre', diagnostic='Paludisme')

    def test_la_consultation_est_calculee_seule(self):
        facture = facturer(self.patient, 'rendez_vous', self.rdv)

        self.assertEqual(facture.montant_total, Decimal('10000'))
        self.assertEqual(facture.part_assurance(), Decimal('7000'))
        self.assertEqual(facture.part_patient(), Decimal('3000'))

    def test_lexamen_a_sa_propre_facture_et_son_propre_calcul(self):
        examen = ExamenMedical.objects.create(
            patient=self.patient, consultation=self.consultation,
            type_examen='Radiographie', date=date(2026, 12, 1))

        facture = facturer(self.patient, 'examen', examen)

        self.assertEqual(facture.montant_total, Decimal('5000'))
        self.assertEqual(facture.part_assurance(), Decimal('3500'))
        self.assertEqual(facture.part_patient(), Decimal('1500'))

    def test_les_trois_services_ne_sont_jamais_additionnes(self):
        """Le cœur de la règle : trois actes, trois factures, trois calculs."""
        examen = ExamenMedical.objects.create(
            patient=self.patient, consultation=self.consultation,
            type_examen='Radiographie', date=date(2026, 12, 1))
        hospitalisation = Hospitalisation.objects.create(
            patient=self.patient, medecin=self.medecin,
            date_entree=date(2026, 12, 1), nombre_jours=1,
            type_chambre='Standard', numero_chambre='12')

        f_consult = facturer(self.patient, 'rendez_vous', self.rdv)
        f_examen = facturer(self.patient, 'examen', examen)
        f_hospi = facturer(self.patient, 'hospitalisation', hospitalisation)

        # Trois factures distinctes, chacune avec son propre reste à charge.
        self.assertEqual(Facture.objects.filter(patient=self.patient).count(), 3)
        self.assertEqual(f_consult.part_patient(), Decimal('3000'))
        self.assertEqual(f_examen.part_patient(), Decimal('1500'))
        self.assertGreater(f_hospi.part_patient(), 0)
        # Aucune facture ne porte le total des trois.
        for facture in (f_consult, f_examen, f_hospi):
            self.assertLess(facture.montant_total, Decimal('30000'))

    def test_chaque_facture_se_regle_et_se_quitte_independamment(self):
        """Payer la consultation ne solde pas l'examen."""
        examen = ExamenMedical.objects.create(
            patient=self.patient, consultation=self.consultation,
            type_examen='Radiographie', date=date(2026, 12, 1))
        f_consult = facturer(self.patient, 'rendez_vous', self.rdv)
        f_examen = facturer(self.patient, 'examen', examen)

        Paiement.objects.create(facture=f_consult, montant=Decimal('3000'),
                                mode_paiement='cash')

        self.assertTrue(f_consult.est_reglee())
        self.assertFalse(Facture.objects.get(pk=f_examen.pk).est_reglee())


@override_settings(ALLOWED_HOSTS=['testserver'])
class AssuranceParMedicamentTests(TestCase):
    """Sur une ordonnance, l'assurance s'applique médicament par médicament."""

    def setUp(self):
        self.assurance = Assurance.objects.create(
            nom='Mutuelle de test', taux_prise_en_charge=Decimal('70'))
        self.patient = Patient.objects.create(
            nom='Traore', prenom='Awa', sexe='Féminin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='0000', email='a@b.c', numero_urgence='0000',
            assurance=self.assurance)
        medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Diag',
            specialite='Généraliste', role='medecin')
        rdv = Rendez_vous.objects.create(
            patient=self.patient, medecin=medecin, date='2026-12-01T09:00')
        consultation = Consultation.objects.create(
            rendez_vous=rdv, motif='Fièvre', diagnostic='Paludisme')
        self.ordonnance = Ordonnance.objects.create(
            consultation=consultation, date=date(2026, 12, 1),
            medicaments='Doliprane, Oméprazole, Efferalgan')

    def servir(self, nom, prix, quantite=1, rembourse=True):
        """Approvisionne puis sert un médicament sur l'ordonnance."""
        medicament = Medicament.objects.create(
            nom=nom, prix_unitaire=Decimal(prix), rembourse=rembourse)
        MouvementStock.objects.create(
            medicament=medicament, type_mouvement='entree', quantite=100,
            prix_unitaire=Decimal(prix))
        MouvementStock.objects.create(
            medicament=medicament, type_mouvement='sortie', quantite=quantite,
            prix_unitaire=Decimal(prix), ordonnance=self.ordonnance,
            patient=self.patient)
        return medicament

    def facture_pharmacie(self):
        facture, _ = Facture.objects.get_or_create(
            patient=self.patient, ordonnance=self.ordonnance,
            defaults={'assurance': self.assurance})
        facture.save()
        facture.refresh_from_db()
        return facture

    def test_tous_rembourses_le_taux_sapplique_a_tout(self):
        self.servir('Doliprane', '2000')
        self.servir('Oméprazole', '5000')
        self.servir('Efferalgan', '1000')

        facture = self.facture_pharmacie()

        self.assertEqual(facture.montant_total, Decimal('8000'))
        self.assertEqual(facture.montant_remboursable, Decimal('8000'))
        self.assertEqual(facture.part_assurance(), Decimal('5600'))
        self.assertEqual(facture.part_patient(), Decimal('2400'))

    def test_un_medicament_non_rembourse_sort_de_lassiette(self):
        """Efferalgan non remboursé : le patient le paie en entier, les
        deux autres restent pris en charge à 70 %."""
        self.servir('Doliprane', '2000')
        self.servir('Oméprazole', '5000')
        self.servir('Efferalgan', '1000', rembourse=False)

        facture = self.facture_pharmacie()

        self.assertEqual(facture.montant_total, Decimal('8000'))
        self.assertEqual(facture.montant_remboursable, Decimal('7000'))
        # 70 % de 7 000, et non de 8 000.
        self.assertEqual(facture.part_assurance(), Decimal('4900'))
        # 2 100 (ticket modérateur) + 1 000 (Efferalgan entier)
        self.assertEqual(facture.part_patient(), Decimal('3100'))

    def test_aucun_medicament_rembourse_le_patient_paie_tout(self):
        self.servir('Efferalgan', '1000', rembourse=False)
        self.servir('Vitamine C', '1500', rembourse=False)

        facture = self.facture_pharmacie()

        self.assertEqual(facture.montant_remboursable, Decimal('0'))
        self.assertEqual(facture.part_assurance(), Decimal('0'))
        self.assertEqual(facture.part_patient(), Decimal('2500'))

    def test_le_detail_montre_la_part_de_chaque_medicament(self):
        self.servir('Doliprane', '2000')
        self.servir('Efferalgan', '1000', rembourse=False)

        facture = self.facture_pharmacie()
        parts = {
            ligne.description: (ligne.part_assurance, ligne.part_patient)
            for groupe in facture.lignes_groupees() for ligne in groupe['lignes']
        }

        self.assertEqual(parts['Médicament — Doliprane'], (Decimal('1400'), Decimal('600')))
        self.assertEqual(parts['Médicament — Efferalgan'], (Decimal('0'), Decimal('1000')))

    def test_la_quantite_est_prise_en_compte(self):
        self.servir('Doliprane', '500', quantite=4)      # 2 000
        self.servir('Efferalgan', '500', quantite=2, rembourse=False)   # 1 000

        facture = self.facture_pharmacie()

        self.assertEqual(facture.montant_total, Decimal('3000'))
        self.assertEqual(facture.part_assurance(), Decimal('1400'))   # 70 % de 2 000
        self.assertEqual(facture.part_patient(), Decimal('1600'))

    def test_un_patient_sans_assurance_paie_tout(self):
        self.patient.assurance = None
        self.patient.save()
        self.servir('Doliprane', '2000')
        facture = Facture.objects.create(
            patient=self.patient, ordonnance=self.ordonnance)

        self.assertEqual(facture.part_assurance(), Decimal('0'))
        self.assertEqual(facture.part_patient(), Decimal('2000'))

    def test_declasser_un_medicament_ne_change_pas_les_factures_passees(self):
        """La ligne garde l'état du médicament au moment de la facturation."""
        medicament = self.servir('Doliprane', '2000')
        facture = self.facture_pharmacie()
        self.assertEqual(facture.part_assurance(), Decimal('1400'))

        medicament.rembourse = False
        medicament.save()
        facture.refresh_from_db()

        # Tant qu'on ne recalcule pas, la facture déjà établie ne bouge pas.
        self.assertEqual(facture.part_assurance(), Decimal('1400'))


@override_settings(ALLOWED_HOSTS=['testserver'])
class EcranPriseEnChargeTests(TestCase):
    """L'écran qui coche les médicaments remboursés, et sa proposition."""

    @classmethod
    def setUpTestData(cls):
        from comptes.roles import installer_roles
        installer_roles()

    def setUp(self):
        from django.contrib.auth.models import User
        from comptes.models import Profil, Role

        utilisateur = User.objects.create_user('pharma', password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur, role=Role.objects.get(code='pharmacien'))
        self.client.force_login(utilisateur)

    def test_la_proposition_ecarte_les_consommables(self):
        from pharmacie.views import proposition_remboursement

        compresses = Medicament.objects.create(
            nom='Compresses stériles', categorie='consommable')

        self.assertFalse(proposition_remboursement(compresses))

    def test_la_proposition_retient_le_generique_et_ecarte_la_marque(self):
        from pharmacie.views import proposition_remboursement

        generique = Medicament.objects.create(
            nom='Amoxicilline', dci='Amoxicilline', categorie='antibiotique')
        marque = Medicament.objects.create(
            nom='Doliprane', dci='Paracétamol', categorie='antalgique')

        self.assertTrue(proposition_remboursement(generique))
        self.assertFalse(proposition_remboursement(marque))

    def test_la_proposition_accepte_un_generique_avec_la_marque_entre_parentheses(self):
        from pharmacie.views import proposition_remboursement

        medicament = Medicament.objects.create(
            nom='Povidone iodée (Bétadine)', dci='Povidone iodée',
            categorie='antiseptique')

        self.assertTrue(proposition_remboursement(medicament))

    def test_enregistrer_coche_et_decoche_en_une_fois(self):
        from django.urls import reverse

        garde = Medicament.objects.create(nom='Amoxicilline', dci='Amoxicilline')
        retire = Medicament.objects.create(nom='Doliprane', dci='Paracétamol')
        self.assertTrue(retire.rembourse)   # coché par défaut

        self.client.post(reverse('pharmacie:remboursement'),
                         {f'rembourse_{garde.pk}': 'on'})

        self.assertTrue(Medicament.objects.get(pk=garde.pk).rembourse)
        self.assertFalse(Medicament.objects.get(pk=retire.pk).rembourse)

    def test_le_dosage_nempeche_pas_de_reconnaitre_le_generique(self):
        """Cas réel du catalogue : DCI « Povidone iodée 10% » pour « Povidone
        iodée (Bétadine) ». Le dosage ne doit pas en faire une marque."""
        from pharmacie.views import proposition_remboursement

        medicament = Medicament.objects.create(
            nom='Povidone iodée (Bétadine)', dci='Povidone iodée 10%',
            categorie='antiseptique')

        self.assertTrue(proposition_remboursement(medicament))


@override_settings(ALLOWED_HOSTS=['testserver'])
class ClassementParCategorieTests(TestCase):
    """Les médicaments s'affichent rangés par famille, pas en vrac."""

    def setUp(self):
        # Les migrations 0002/0005/0007 installent le catalogue réel de la
        # clinique (41 médicaments). On part d'un catalogue vide pour que ces
        # tests portent sur le classement et non sur le contenu du catalogue.
        Medicament.objects.all().delete()

    def test_les_groupes_suivent_lordre_clinique_du_modele(self):
        from pharmacie.views import grouper_par_categorie

        Medicament.objects.create(nom='Compresses', categorie='consommable')
        Medicament.objects.create(nom='Amoxicilline', categorie='antibiotique')
        Medicament.objects.create(nom='Paracétamol', categorie='antalgique')

        groupes = grouper_par_categorie(list(Medicament.objects.all()))
        codes = [g['code'] for g in groupes]

        # antalgique vient avant antibiotique, qui vient avant consommable.
        self.assertEqual(codes, ['antalgique', 'antibiotique', 'consommable'])

    def test_un_groupe_vide_nest_pas_affiche(self):
        from pharmacie.views import grouper_par_categorie

        Medicament.objects.create(nom='Amoxicilline', categorie='antibiotique')

        groupes = grouper_par_categorie(list(Medicament.objects.all()))

        self.assertEqual(len(groupes), 1)
        self.assertEqual(groupes[0]['libelle'], 'Antibiotique')

    def test_un_medicament_sans_categorie_nest_pas_perdu(self):
        from pharmacie.views import grouper_par_categorie

        Medicament.objects.create(nom='Produit mystère', categorie='')

        groupes = grouper_par_categorie(list(Medicament.objects.all()))

        self.assertEqual(groupes[-1]['libelle'], 'Non classé')
        self.assertEqual(len(groupes[-1]['medicaments']), 1)

    def test_un_nouveau_medicament_rejoint_sa_famille(self):
        """Ce que demandait Aïcha : enregistré en analgésique, il apparaît
        dans le groupe des analgésiques, sans rien faire de plus."""
        from pharmacie.views import grouper_par_categorie

        Medicament.objects.create(nom='Amoxicilline', categorie='antibiotique')
        Medicament.objects.create(nom='Tramadol', categorie='antalgique')

        groupes = {g['code']: g for g in
                   grouper_par_categorie(list(Medicament.objects.all()))}

        noms = [m.nom for m in groupes['antalgique']['medicaments']]
        self.assertEqual(noms, ['Tramadol'])

    def test_le_catalogue_de_lordonnance_est_trie_par_famille(self):
        from django.contrib.auth.models import User
        from comptes.models import Profil, Role
        from comptes.roles import installer_roles
        from django.urls import reverse

        installer_roles()
        Medicament.objects.create(nom='Compresses', categorie='consommable', actif=True)
        Medicament.objects.create(nom='Paracétamol', categorie='antalgique', actif=True)
        Medicament.objects.create(nom='Amoxicilline', categorie='antibiotique', actif=True)

        medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Diag',
            specialite='Généraliste', role='medecin')
        utilisateur = User.objects.create_user('doc', password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur, role=Role.objects.get(code='medecin'),
                              medecin=medecin)
        self.client.force_login(utilisateur)

        reponse = self.client.get(reverse('consultation:ordonnance_ajouter'))
        familles = [m['categorie'] for m in reponse.context['catalogue']]

        self.assertEqual(familles, ['Antalgique / Antidouleur', 'Antibiotique',
                                    'Consommable / Matériel médical'])
