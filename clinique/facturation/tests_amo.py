"""L'AMO à la pharmacie, et le retrait de Takaful.

Le pharmacien doit savoir, avant de valider, ce que l'AMO ne prend pas en charge ;
la facture créée en dispensant doit reprendre l'assurance du patient.
"""
import importlib
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Consultation, Ordonnance, Rendez_vous
from facturation.models import Assurance, Facture
from facturation.pdf import medicaments_non_couverts
from patients.models import Patient
from personnel.models import Medecin
from pharmacie.models import Medicament, MouvementStock


def creer_patient(assurance=None, **champs):
    return Patient.objects.create(
        nom='Traore', prenom='Awa', sexe='Féminin', date_naissance=date(1990, 1, 1),
        adresse='Bamako', telephone='0000', email='a@b.c', numero_urgence='0000',
        assurance=assurance, **champs)


def creer_utilisateur(nom, role):
    utilisateur = User.objects.create_user(nom, password='x')
    Profil.objects.update_or_create(user=utilisateur, defaults={'role': Role.objects.get(code=role)})
    return utilisateur


@override_settings(ALLOWED_HOSTS=['testserver'])
class DispensationAMOTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        self.amo, _ = Assurance.objects.get_or_create(
            nom='AMO', defaults={'taux_prise_en_charge': Decimal('70')})
        self.doliprane = self.medicament('Doliprane Test', '1000', rembourse=False)
        self.amoxicilline = self.medicament('Amoxicilline Test', '2500', rembourse=True)
        self.client.force_login(creer_utilisateur('pharma', 'pharmacien'))

    def medicament(self, nom, prix, rembourse):
        medicament = Medicament.objects.create(nom=nom, prix_unitaire=Decimal(prix), rembourse=rembourse)
        MouvementStock.objects.create(medicament=medicament, type_mouvement='entree', quantite=50,
                                      prix_unitaire=Decimal(prix))
        return medicament

    def ordonnance(self, patient):
        medecin = Medecin.objects.create(nom='House', prenom='G', telephone='1', service='Diag',
                                         specialite='Généraliste', role='medecin')
        rdv = Rendez_vous.objects.create(patient=patient, medecin=medecin, date='2026-12-01T09:00')
        consultation = Consultation.objects.create(rendez_vous=rdv, motif='Fièvre', diagnostic='Paludisme')
        return Ordonnance.objects.create(
            consultation=consultation, date=date(2026, 12, 1),
            medicaments='- Doliprane Test : 1 matin\n- Amoxicilline Test : 1 soir')

    def dispenser(self, patient, ordonnance):
        return self.client.post(reverse('pharmacie:sortie_stock'), {
            'patient': patient.pk, 'ordonnance': ordonnance.pk,
            'ligne_med': [self.doliprane.pk, self.amoxicilline.pk], 'ligne_qte': [2, 1],
        })

    def test_la_facture_de_pharmacie_reprend_lamo_du_patient(self):
        patient = creer_patient(self.amo, numero_assure='AMO-1')
        ordonnance = self.ordonnance(patient)
        self.dispenser(patient, ordonnance)

        facture = Facture.objects.get(ordonnance=ordonnance)
        self.assertEqual(facture.assurance, self.amo)
        self.assertEqual(facture.taux_prise_en_charge, self.amo.taux_prise_en_charge)
        self.assertEqual(facture.montant_total, Decimal('4500'))
        self.assertEqual(facture.montant_remboursable, Decimal('2500'))
        self.assertEqual(facture.part_assurance(), Decimal('1750'))
        self.assertEqual(facture.part_patient(), Decimal('2750'))

    def test_un_patient_sans_assurance_paie_tout(self):
        patient = creer_patient()
        ordonnance = self.ordonnance(patient)
        self.dispenser(patient, ordonnance)

        facture = Facture.objects.get(ordonnance=ordonnance)
        self.assertIsNone(facture.assurance)
        self.assertEqual(facture.part_patient(), Decimal('4500'))

    def test_un_second_passage_garde_la_meme_facture_et_lamo(self):
        patient = creer_patient(self.amo)
        ordonnance = self.ordonnance(patient)
        self.client.post(reverse('pharmacie:sortie_stock'), {
            'patient': patient.pk, 'ordonnance': ordonnance.pk,
            'ligne_med': [self.amoxicilline.pk], 'ligne_qte': [1]})
        self.client.post(reverse('pharmacie:sortie_stock'), {
            'patient': patient.pk, 'ordonnance': ordonnance.pk,
            'ligne_med': [self.doliprane.pk], 'ligne_qte': [2]})

        facture = Facture.objects.get(ordonnance=ordonnance)
        self.assertEqual(facture.assurance, self.amo)
        self.assertEqual(facture.part_assurance(), Decimal('1750'))

    def test_le_pharmacien_est_prevenu_apres_lenregistrement(self):
        patient = creer_patient(self.amo)
        reponse = self.dispenser(patient, self.ordonnance(patient))

        textes = [str(m) for m in get_messages(reponse.wsgi_request)]
        self.assertTrue(any('Part AMO' in t and '1 750' in t and '2 750' in t for t in textes), textes)
        self.assertTrue(any("Non pris en charge par l'AMO" in t and 'Doliprane' in t for t in textes), textes)

    def test_la_sortie_manuelle_previent_aussi(self):
        patient = creer_patient(self.amo)
        ordonnance = self.ordonnance(patient)
        reponse = self.client.post(reverse('pharmacie:sortie_stock'), {
            'medicament': self.doliprane.pk, 'quantite': 1, 'prix_unitaire': '1000',
            'patient': patient.pk, 'ordonnance': ordonnance.pk})

        self.assertEqual(Facture.objects.get(ordonnance=ordonnance).assurance, self.amo)
        textes = [str(m) for m in get_messages(reponse.wsgi_request)]
        self.assertTrue(any("Non pris en charge par l'AMO" in t for t in textes), textes)

    def test_lecran_de_saisie_recoit_ce_quil_faut_pour_alerter(self):
        patient = creer_patient(self.amo)
        sans_assurance = creer_patient()
        self.ordonnance(patient)

        reponse = self.client.get(reverse('pharmacie:sortie_stock'))

        assurances = reponse.context['assurance_par_patient']
        self.assertEqual(assurances[str(patient.pk)]['nom'], 'AMO')
        self.assertNotIn(str(sans_assurance.pk), assurances)
        lignes = reponse.context['ordo_par_patient'][str(patient.pk)][0]['lignes']
        self.assertEqual({l['nom']: l['rembourse'] for l in lignes}, {'Doliprane Test': False, 'Amoxicilline Test': True})
        self.assertContains(reponse, 'data-rembourse="0"')

    def test_la_facture_et_le_pdf_nomment_le_medicament_non_couvert(self):
        patient = creer_patient(self.amo)
        ordonnance = self.ordonnance(patient)
        self.dispenser(patient, ordonnance)
        facture = Facture.objects.get(ordonnance=ordonnance)

        page = self.client.get(reverse('facturation:detail', args=[facture.pk])).content.decode()
        self.assertIn("Non pris en charge par l'AMO", page)
        self.assertEqual(medicaments_non_couverts(facture), ['Doliprane Test'])
        pdf = self.client.get(reverse('facturation:facture_pdf', args=[facture.pk]))
        self.assertEqual(pdf.status_code, 200)

    def test_sans_assurance_le_pdf_ne_signale_rien(self):
        patient = creer_patient()
        ordonnance = self.ordonnance(patient)
        self.dispenser(patient, ordonnance)
        self.assertEqual(medicaments_non_couverts(Facture.objects.get(ordonnance=ordonnance)), [])

    def test_lapercu_du_formulaire_connait_la_part_assurable(self):
        patient = creer_patient(self.amo)
        ordonnance = self.ordonnance(patient)
        self.dispenser(patient, ordonnance)
        self.client.force_login(creer_utilisateur('chef', 'admin'))

        reponse = self.client.get(reverse('facturation:ajouter'))

        ordo = next(o for o in reponse.context['ordonnances'] if o.pk == ordonnance.pk)
        self.assertEqual(ordo.montant_dispense, Decimal('4500'))
        self.assertEqual(ordo.montant_assurable, Decimal('2500'))


@override_settings(ALLOWED_HOSTS=['testserver'])
class RetraitTakafulTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def retirer(self):
        module = importlib.import_module('facturation.migrations.0022_retirer_takaful')
        module.retirer_takaful(apps, SimpleNamespace(connection=connection))

    def test_une_base_neuve_na_plus_takaful(self):
        self.assertFalse(Assurance.objects.filter(nom__startswith='Takaful').exists())
        self.assertTrue(Assurance.objects.filter(nom='AMO').exists())

    def test_les_patients_quittent_takaful_et_son_numero(self):
        takaful = Assurance.objects.create(nom='Takaful 70%', taux_prise_en_charge=Decimal('70'))
        patient = creer_patient(takaful, numero_assure='TK-1')
        self.retirer()

        patient.refresh_from_db()
        self.assertIsNone(patient.assurance)
        self.assertEqual(patient.numero_assure, '')

    def test_les_anciennes_factures_ne_bougent_pas(self):
        takaful = Assurance.objects.create(nom='Takaful 100%', taux_prise_en_charge=Decimal('100'))
        patient = creer_patient(takaful)
        facture = Facture.objects.create(patient=patient, assurance=takaful)
        Facture.objects.filter(pk=facture.pk).update(montant_total=Decimal('8000'), montant_remboursable=Decimal('8000'))
        facture.refresh_from_db()
        part_avant = facture.part_assurance()
        self.retirer()

        facture.refresh_from_db()
        takaful.refresh_from_db()
        self.assertFalse(takaful.actif)
        self.assertEqual(facture.assurance, takaful)
        self.assertEqual(facture.part_assurance(), part_avant)

    def test_une_formule_sans_facture_disparait(self):
        Assurance.objects.create(nom='Takaful 70%', taux_prise_en_charge=Decimal('70'))
        self.retirer()
        self.assertFalse(Assurance.objects.filter(nom='Takaful 70%').exists())

    def test_lamo_nest_pas_touchee(self):
        amo = Assurance.objects.get(nom='AMO')
        patient = creer_patient(amo, numero_assure='AMO-9')
        self.retirer()

        patient.refresh_from_db()
        amo.refresh_from_db()
        self.assertTrue(amo.actif)
        self.assertEqual(patient.assurance, amo)
        self.assertEqual(patient.numero_assure, 'AMO-9')

    def test_on_ne_peut_plus_ajouter_ni_supprimer_une_assurance(self):
        for nom, args in (('assurance_ajouter', []), ('assurance_supprimer', [1])):
            with self.assertRaises(NoReverseMatch):
                reverse(f'facturation:{nom}', args=args)

    def test_la_page_ne_montre_que_les_assurances_actives(self):
        Assurance.objects.create(nom='Takaful 70%', taux_prise_en_charge=Decimal('70'), actif=False)
        self.client.force_login(creer_utilisateur('chef', 'admin'))

        reponse = self.client.get(reverse('facturation:assurances'))

        self.assertContains(reponse, 'AMO')
        self.assertNotContains(reponse, 'Takaful')

    def test_modifier_une_ancienne_facture_ne_lui_fait_pas_perdre_son_assurance(self):
        takaful = Assurance.objects.create(nom='Takaful 100%', taux_prise_en_charge=Decimal('100'), actif=False)
        facture = Facture.objects.create(patient=creer_patient(), assurance=takaful)
        self.client.force_login(creer_utilisateur('chef', 'admin'))

        reponse = self.client.get(reverse('facturation:modifier', args=[facture.pk]))
        self.assertIn(takaful, reponse.context['assurances'])

        neuve = self.client.get(reverse('facturation:ajouter'))
        self.assertNotIn(takaful, neuve.context['assurances'])
