"""Confidentialité : un médecin ne voit que ses propres patients."""
from datetime import date, datetime

from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth.models import User

from comptes.models import Role, Profil
from comptes.roles import installer_roles
from personnel.models import Medecin
from patients.models import Patient
from consultation.models import Rendez_vous


def _patient(nom):
    return Patient.objects.create(
        nom=nom, prenom='Test', sexe='M', date_naissance=date(1990, 1, 1),
        adresse='—', telephone='0000', email='a@b.c', numero_urgence='0000',
    )


@override_settings(ALLOWED_HOSTS=['testserver'])
class MedecinVoitSesPatientsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Les vrais rôles de la clinique, avec leurs permissions. Les vues sont
        # protégées par `permission_required` : un rôle « médecin » créé à la
        # main et sans permission serait refusé à l'entrée (redirection 302) et
        # le test ne vérifierait plus rien du cloisonnement des dossiers.
        # Une seule fois pour toute la classe : le catalogue fait ~70 permissions.
        installer_roles()

    def setUp(self):
        role = Role.objects.get(code='medecin')

        self.med_a = Medecin.objects.create(
            nom='Alpha', prenom='A', telephone='1', service='Cardio',
            specialite='Cardiologie', role='medecin')
        self.med_b = Medecin.objects.create(
            nom='Beta', prenom='B', telephone='2', service='Derma',
            specialite='Dermatologie', role='medecin')

        self.user_a = User.objects.create_user('doca', password='x')
        Profil.objects.create(user=self.user_a, role=role, medecin=self.med_a)

        # Patient du médecin A (a un rendez-vous avec lui)
        self.pat_a = _patient('PatientDeA')
        Rendez_vous.objects.create(
            patient=self.pat_a, medecin=self.med_a,
            date=timezone.make_aware(datetime(2026, 1, 10, 9, 0)))

        # Patient du médecin B
        self.pat_b = _patient('PatientDeB')
        Rendez_vous.objects.create(
            patient=self.pat_b, medecin=self.med_b,
            date=timezone.make_aware(datetime(2026, 1, 10, 10, 0)))

    def test_liste_ne_montre_que_ses_patients(self):
        self.client.force_login(self.user_a)
        r = self.client.get('/patients/')
        self.assertEqual(r.status_code, 200)
        pks = [p.pk for p in r.context['patients']]
        self.assertIn(self.pat_a.pk, pks)
        self.assertNotIn(self.pat_b.pk, pks)

    def test_recherche_par_nom_complet(self):
        # « nom prénom » (et ordre inversé) doivent trouver le patient,
        # même si aucun champ seul ne contient la chaîne entière.
        self.client.force_login(self.user_a)
        for terme in ['PatientDeA Test', 'Test PatientDeA']:
            r = self.client.get('/patients/', {'q': terme})
            pks = [p.pk for p in r.context['patients']]
            self.assertEqual(pks, [self.pat_a.pk], f"échec pour {terme!r}")

    def test_detail_patient_d_un_autre_medecin_est_refuse(self):
        self.client.force_login(self.user_a)
        r = self.client.get(f'/patients/{self.pat_b.pk}/')
        # On vérifie la DESTINATION, pas seulement le code 302 : un refus de
        # permission renvoie lui aussi un 302, mais vers le tableau de bord.
        # Sans cette précision, le test resterait vert alors même que le
        # cloisonnement ne serait plus exercé du tout.
        self.assertRedirects(r, '/patients/')

    def test_detail_de_son_patient_est_accessible(self):
        self.client.force_login(self.user_a)
        r = self.client.get(f'/patients/{self.pat_a.pk}/')
        self.assertEqual(r.status_code, 200)

    def test_admin_voit_tous_les_patients(self):
        boss = User.objects.create_superuser('boss', 'b@b.c', 'x')
        self.client.force_login(boss)
        r = self.client.get('/patients/')
        pks = [p.pk for p in r.context['patients']]
        self.assertIn(self.pat_a.pk, pks)
        self.assertIn(self.pat_b.pk, pks)
