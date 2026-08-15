"""Tests de la règle « on paie avant d'être soigné » (voir facturation/regles.py).

La consultation, l'examen et l'hospitalisation sont prépayés : la facture est
créée dès l'enregistrement de l'acte, et l'acte est interdit tant qu'elle n'est
pas soldée. La pharmacie fait exception (facture après dispensation).
"""
from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth.models import User

from patients.models import Patient
from personnel.models import Medecin
from consultation.models import (
    Rendez_vous, Consultation, ExamenMedical, ResultatExamen, Hospitalisation,
)
from facturation.models import Facture, Assurance, Paiement, Tarif
from facturation.regles import blocage


@override_settings(ALLOWED_HOSTS=['testserver'])
class PaiementAvantSoinTests(TestCase):

    def setUp(self):
        self.medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Diag',
            specialite='Généraliste', role='medecin')
        self.patient = Patient.objects.create(
            nom='Traore', prenom='Awa', sexe='Féminin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='0000', email='a@b.c', numero_urgence='0000')

        Tarif.objects.create(type_service='consultation', specialite='Généraliste',
                             nom='Consultation généraliste', prix=Decimal('3000'))
        Tarif.objects.create(type_service='examen', specialite='Radiographie',
                             nom='Radiographie', prix=Decimal('8000'))
        Tarif.objects.create(type_service='hospitalisation', specialite='vip',
                             nom='Chambre VIP', prix=Decimal('20000'))

        self.client.force_login(
            User.objects.create_superuser('boss_prepaiement', 'b@b.c', 'x'))

    # ── Utilitaires ──

    def _prendre_rdv(self):
        r = self.client.post('/consultation/rdv/ajouter/', {
            'patient': self.patient.pk, 'medecin': self.medecin.pk,
            'date': '2026-03-02 09:00', 'statut': 'programme',
        })
        self.assertEqual(r.status_code, 302)
        return Rendez_vous.objects.get()

    def _regler(self, facture):
        Paiement.objects.create(facture=facture, montant=facture.part_patient(),
                                mode_paiement='cash')
        facture.refresh_from_db()
        return facture

    def _consultation_reglee(self):
        """Un rendez-vous payé, puis la consultation qui en découle."""
        rdv = self._prendre_rdv()
        self._regler(Facture.objects.get(rendez_vous=rdv))
        return Consultation.objects.create(rendez_vous=rdv, motif='m', diagnostic='d')

    def _prescrire_examen(self, consultation):
        r = self.client.post('/consultation/examens/ajouter/', {
            'patient': self.patient.pk, 'consultation': consultation.pk,
            'medecin': self.medecin.pk, 'type_examen': 'Radiographie', 'motif': '',
        })
        self.assertEqual(r.status_code, 302)
        return ExamenMedical.objects.get()

    def _admettre(self):
        r = self.client.post('/consultation/hospitalisations/ajouter/', {
            'patient': self.patient.pk, 'medecin': self.medecin.pk,
            'numero_chambre': '101', 'etat_clinique': 'stable',
            'nombre_jours': '2', 'date_entree': '2026-03-02',
        })
        self.assertEqual(r.status_code, 302)
        return Hospitalisation.objects.get()

    # ── Consultation ──

    def test_prendre_un_rdv_cree_la_facture_de_consultation(self):
        rdv = self._prendre_rdv()
        facture = Facture.objects.get(rendez_vous=rdv)
        self.assertEqual(facture.montant_total, Decimal('3000'))
        self.assertEqual(facture.statut, 'non payé')

    def test_consultation_refusee_tant_que_le_rdv_n_est_pas_regle(self):
        rdv = self._prendre_rdv()
        r = self.client.post('/consultation/ajouter/', {
            'rendez_vous': rdv.pk, 'motif': 'Fièvre', 'diagnostic': 'Grippe',
        })
        self.assertEqual(r.status_code, 200)          # reste sur le formulaire
        self.assertFalse(Consultation.objects.exists())

    def test_consultation_acceptee_une_fois_le_rdv_regle(self):
        rdv = self._prendre_rdv()
        self._regler(Facture.objects.get(rendez_vous=rdv))
        r = self.client.post('/consultation/ajouter/', {
            'rendez_vous': rdv.pk, 'motif': 'Fièvre', 'diagnostic': 'Grippe',
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Consultation.objects.filter(rendez_vous=rdv).exists())

    def test_paiement_partiel_ne_debloque_pas(self):
        rdv = self._prendre_rdv()
        facture = Facture.objects.get(rendez_vous=rdv)
        Paiement.objects.create(facture=facture, montant=Decimal('1000'),
                                mode_paiement='cash')
        self.assertIsNotNone(blocage('rendez_vous', rdv))

    def test_assurance_a_100_pourcent_ne_bloque_pas(self):
        """Rien à payer au guichet : l'acte doit passer immédiatement."""
        self.patient.assurance = Assurance.objects.create(
            nom='Prise en charge totale', taux_prise_en_charge=Decimal('100'))
        self.patient.save()
        rdv = self._prendre_rdv()
        self.assertEqual(Facture.objects.get(rendez_vous=rdv).part_patient(),
                         Decimal('0'))
        self.assertIsNone(blocage('rendez_vous', rdv))

    # ── Examen ──

    def test_prescrire_un_examen_cree_sa_facture(self):
        examen = self._prescrire_examen(self._consultation_reglee())
        self.assertEqual(Facture.objects.get(examen=examen).montant_total,
                         Decimal('8000'))

    def test_resultat_refuse_tant_que_l_examen_n_est_pas_regle(self):
        examen = self._prescrire_examen(self._consultation_reglee())
        r = self.client.post('/consultation/resultats/ajouter/', {
            'examen': examen.pk, 'resultat': 'RAS', 'observations': '',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ResultatExamen.objects.exists())

    def test_resultat_accepte_une_fois_l_examen_regle(self):
        examen = self._prescrire_examen(self._consultation_reglee())
        self._regler(Facture.objects.get(examen=examen))
        r = self.client.post('/consultation/resultats/ajouter/', {
            'examen': examen.pk, 'resultat': 'RAS', 'observations': '',
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(ResultatExamen.objects.filter(examen=examen).exists())

    # ── Hospitalisation ──

    def test_admission_facturee_et_non_confirmee_avant_paiement(self):
        hospit = self._admettre()
        facture = Facture.objects.get(hospitalisation=hospit)
        self.assertEqual(facture.montant_total, Decimal('40000'))   # 20 000 × 2 nuits
        self.assertFalse(hospit.est_admis())
        self.assertEqual(hospit.etat()['code'], 'attente_paiement')

    def test_admission_confirmee_une_fois_le_sejour_regle(self):
        hospit = self._admettre()
        self._regler(Facture.objects.get(hospitalisation=hospit))
        hospit = Hospitalisation.objects.get(pk=hospit.pk)
        self.assertTrue(hospit.est_admis())
        self.assertEqual(hospit.etat()['code'], 'stable')

    def test_sejour_rallonge_repasse_en_attente_de_paiement(self):
        """Deux nuits de plus = plus d'argent dû : l'admission n'est plus confirmée."""
        hospit = self._admettre()
        self._regler(Facture.objects.get(hospitalisation=hospit))
        r = self.client.post(f'/consultation/hospitalisations/{hospit.pk}/modifier/', {
            'numero_chambre': '101', 'etat_clinique': 'stable',
            'nombre_jours': '4', 'date_entree': '2026-03-02',
        })
        self.assertEqual(r.status_code, 302)
        facture = Facture.objects.get(hospitalisation=hospit)
        self.assertEqual(facture.montant_total, Decimal('80000'))
        self.assertFalse(Hospitalisation.objects.get(pk=hospit.pk).est_admis())

    # ── Pharmacie : l'exception ──

    def test_la_pharmacie_reste_facturee_apres_la_dispensation(self):
        """Aucune facture n'est créée à la prescription : le montant n'est connu
        qu'une fois les médicaments servis."""
        from consultation.models import Ordonnance
        consultation = self._consultation_reglee()
        ordonnance = Ordonnance.objects.create(
            consultation=consultation, date=date(2026, 3, 2),
            medicaments='Paracétamol 500mg')
        self.assertFalse(Facture.objects.filter(ordonnance=ordonnance).exists())
