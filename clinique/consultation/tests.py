"""Tests des barres de recherche des listes (RDV, consultations, ordonnances)."""
from datetime import date, datetime

from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth.models import User

from patients.models import Patient
from personnel.models import Medecin
from consultation.models import (
    Rendez_vous, Consultation, Ordonnance, Traitement, AdministrationTraitement,
)


def _patient(nom, prenom='X'):
    return Patient.objects.create(
        nom=nom, prenom=prenom, sexe='M', date_naissance=date(1990, 1, 1),
        adresse='—', telephone='0000', email='a@b.c', numero_urgence='0000',
    )


def _aware(y, mo, d, h):
    return timezone.make_aware(datetime(y, mo, d, h, 0))


@override_settings(ALLOWED_HOSTS=['testserver'])
class RechercheListesTests(TestCase):
    def setUp(self):
        self.med = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Diag',
            specialite='Généraliste', role='medecin', mot_de_passe='x')

        self.dupont = _patient('Dupont', 'Jean')
        self.martin = _patient('Martin', 'Lucie')

        self.rdv_dupont = Rendez_vous.objects.create(
            patient=self.dupont, medecin=self.med, date=_aware(2026, 2, 1, 9))
        self.rdv_martin = Rendez_vous.objects.create(
            patient=self.martin, medecin=self.med, date=_aware(2026, 2, 1, 10))

        self.cons_dupont = Consultation.objects.create(
            rendez_vous=self.rdv_dupont, motif='Fièvre', diagnostic='Grippe')
        self.cons_martin = Consultation.objects.create(
            rendez_vous=self.rdv_martin, motif='Toux', diagnostic='Bronchite')

        self.ord_dupont = Ordonnance.objects.create(
            consultation=self.cons_dupont, date=date(2026, 2, 1),
            medicaments='Paracétamol 500mg')
        self.ord_martin = Ordonnance.objects.create(
            consultation=self.cons_martin, date=date(2026, 2, 1),
            medicaments='Amoxicilline')

        self.boss = User.objects.create_superuser('boss', 'b@b.c', 'x')
        self.client.force_login(self.boss)

    def test_recherche_rdv_par_patient(self):
        r = self.client.get('/consultation/rdv/', {'q': 'Dupont'})
        self.assertEqual(r.status_code, 200)
        pks = [x.pk for x in r.context['resultats_recherche']]
        self.assertIn(self.rdv_dupont.pk, pks)
        self.assertNotIn(self.rdv_martin.pk, pks)

    def test_recherche_rdv_par_nom_complet(self):
        # Le bug d'origine : taper « Dupont Jean » ne renvoyait rien.
        for terme in ['Dupont Jean', 'Jean Dupont']:
            r = self.client.get('/consultation/rdv/', {'q': terme})
            pks = [x.pk for x in r.context['resultats_recherche']]
            self.assertEqual(pks, [self.rdv_dupont.pk], f"échec pour {terme!r}")

    def test_recherche_consultation_par_patient(self):
        r = self.client.get('/consultation/', {'q': 'Dupont'})
        self.assertEqual(r.status_code, 200)
        pks = [c.pk for c in r.context['consultations']]
        self.assertIn(self.cons_dupont.pk, pks)
        self.assertNotIn(self.cons_martin.pk, pks)

    def test_recherche_consultation_par_motif(self):
        r = self.client.get('/consultation/', {'q': 'Toux'})
        pks = [c.pk for c in r.context['consultations']]
        self.assertEqual(pks, [self.cons_martin.pk])

    def test_recherche_ordonnance_par_medicament(self):
        r = self.client.get('/consultation/ordonnances/', {'q': 'Amoxicilline'})
        self.assertEqual(r.status_code, 200)
        pks = [o.pk for o in r.context['ordonnances']]
        self.assertIn(self.ord_martin.pk, pks)
        self.assertNotIn(self.ord_dupont.pk, pks)

    def test_recherche_ordonnance_par_patient(self):
        r = self.client.get('/consultation/ordonnances/', {'q': 'Dupont'})
        pks = [o.pk for o in r.context['ordonnances']]
        self.assertEqual(pks, [self.ord_dupont.pk])

    def test_sans_recherche_tout_est_visible(self):
        r = self.client.get('/consultation/')
        pks = [c.pk for c in r.context['consultations']]
        self.assertIn(self.cons_dupont.pk, pks)
        self.assertIn(self.cons_martin.pk, pks)


@override_settings(ALLOWED_HOSTS=['testserver'])
class SuiviTraitementTests(TestCase):
    """Suivi temps réel : l'endpoint JSON reflète l'évolution du traitement."""

    def setUp(self):
        self.pat = _patient('Traore', 'Awa')
        self.t = Traitement.objects.create(
            patient=self.pat, description='Perfusion quotidienne', duree=5)
        AdministrationTraitement.objects.create(traitement=self.t, note='Dose 1')
        self.boss = User.objects.create_superuser('boss', 'b@b.c', 'x')
        self.client.force_login(self.boss)

    def test_suivi_json_structure(self):
        r = self.client.get(f'/consultation/traitements/{self.t.pk}/suivi.json')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d['count'], 1)
        self.assertEqual(d['statut'], 'prescrit')
        self.assertEqual(d['administrations'][0]['note'], 'Dose 1')
        self.assertIn('pourcentage', d)
        self.assertIn('maj', d)

    def test_suivi_reflete_nouvelle_administration(self):
        AdministrationTraitement.objects.create(traitement=self.t, note='Dose 2')
        d = self.client.get(f'/consultation/traitements/{self.t.pk}/suivi.json').json()
        self.assertEqual(d['count'], 2)

    def test_detail_fournit_la_progression(self):
        r = self.client.get(f'/consultation/traitements/{self.t.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('progression', r.context)
        self.assertEqual(r.context['progression']['duree'], 5)
