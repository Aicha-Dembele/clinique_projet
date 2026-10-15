"""Le plan de l'établissement : 30 chambres, dont quatre d'urgence.

Deux règles tenues ici :

  - le plan est FIXE et connu du code — on ne peut pas hospitaliser dans une
    chambre qui n'existe pas ;
  - les quatre chambres d'urgence sont le dernier recours de la clinique.
    Si des séjours ordinaires les occupent, le blessé qui arrive à trois
    heures du matin n'a nulle part où aller.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Hospitalisation
from facturation.models import Tarif
from patients.models import Patient


class PlanDesChambresTests(TestCase):

    def test_la_clinique_compte_trente_chambres(self):
        self.assertEqual(len(Hospitalisation.plan_chambres()), 30)

    def test_la_repartition(self):
        par_type = {}
        for _, type_ in Hospitalisation.plan_chambres():
            par_type[type_] = par_type.get(type_, 0) + 1

        self.assertEqual(par_type, {'urgence': 4, 'vip': 6, 'double': 8, 'simple': 12})

    def test_les_numeros_ne_se_repetent_pas(self):
        numeros = [n for n, _ in Hospitalisation.plan_chambres()]

        self.assertEqual(len(numeros), len(set(numeros)))

    def test_les_chambres_durgence_sont_au_rez_de_chaussee(self):
        """On ne monte pas un blessé par l'escalier."""
        urgences = [n for n, t in Hospitalisation.plan_chambres() if t == 'urgence']

        self.assertEqual(urgences, ['001', '002', '003', '004'])

    def test_une_chambre_durgence_naccueille_quun_patient(self):
        self.assertEqual(Hospitalisation.capacite_pour('urgence'), 1)

    def test_les_chambres_de_lhistorique_existent_toujours(self):
        """103 et 201 ont déjà servi : le nouveau plan ne doit pas les perdre."""
        for numero in ('103', '201'):
            with self.subTest(chambre=numero):
                self.assertIsNotNone(Hospitalisation.type_pour_numero(numero))

    def test_les_anciennes_chambres_retirees_nexistent_plus(self):
        """Le 4e étage a disparu, et chaque étage s'est resserré.

        310 existe toujours (les simples vont de 301 à 312) : ce sont 107,
        209 et tout le 4e qui ont été retirés en passant de 40 à 30.
        """
        for numero in ('401', '410', '107', '209', '313'):
            with self.subTest(chambre=numero):
                self.assertIsNone(Hospitalisation.type_pour_numero(numero))


class ChambreUrgenceReserveeTests(TestCase):
    """La règle qui protège les quatre chambres d'urgence."""

    def test_un_patient_critique_y_a_droit(self):
        self.assertIsNone(
            Hospitalisation.blocage_chambre_urgence('urgence', 'critique'))

    def test_un_patient_stable_est_refuse(self):
        refus = Hospitalisation.blocage_chambre_urgence('urgence', 'stable')

        self.assertIsNotNone(refus)
        self.assertIn('critique', refus)

    def test_les_autres_chambres_ne_sont_pas_concernees(self):
        for type_ in ('vip', 'double', 'simple'):
            with self.subTest(type=type_):
                self.assertIsNone(
                    Hospitalisation.blocage_chambre_urgence(type_, 'stable'))


@override_settings(ALLOWED_HOSTS=['testserver'])
class AffectationChambreTests(TestCase):
    """La règle appliquée pour de vrai, à travers le formulaire."""

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        Tarif.objects.create(type_service='hospitalisation', specialite='Urgence',
                             nom='Chambre urgence', prix=Decimal('20000'))
        self.patient = Patient.objects.create(
            nom='Keita', prenom='Moussa', sexe='Masculin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='70000000', email='k@example.com', numero_urgence='70000001')

        utilisateur = User.objects.create_user('recept', password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur,
                              role=Role.objects.get(code='receptionniste'))
        self.client.force_login(utilisateur)

    def hospitaliser(self, **remplacements):
        donnees = {
            'patient': self.patient.pk,
            'numero_chambre': '001',
            'etat_clinique': 'stable',
            'date_entree': '2026-10-15',
            'motif': 'Surveillance',
        }
        donnees.update(remplacements)
        return self.client.post(reverse('consultation:hospit_ajouter'), donnees)

    def test_un_sejour_ordinaire_ne_prend_pas_une_chambre_durgence(self):
        self.hospitaliser(numero_chambre='001', etat_clinique='stable')

        self.assertEqual(Hospitalisation.objects.count(), 0)

    def test_une_chambre_retiree_du_plan_est_refusee(self):
        self.hospitaliser(numero_chambre='410')

        self.assertEqual(Hospitalisation.objects.count(), 0)
