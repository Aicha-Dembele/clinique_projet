"""La pharmacie appartient au pharmacien, pas à l'accueil.

La réception a longtemps eu les quatre permissions de pharmacie
(`pharmacie.view`, `medicament.manage`, `stock.entree`, `stock.sortie`) :
elle voyait donc le stock, le catalogue, les fournisseurs et les commandes.
Ce n'est pas son métier. Ces tests tiennent la frontière, dans les deux
sens — la réception est dehors, le pharmacien est dedans.

La séparation des CAISSES, elle, est testée à part dans
`facturation/tests_caisses.py` : la réception encaisse les soins, le
comptoir de la pharmacie encaisse les médicaments.
"""
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import Profil, Role
from comptes.roles import ROLE_PERMISSIONS, installer_roles

#: Les pages que la réception ne doit jamais atteindre.
PAGES_PHARMACIE = [
    'pharmacie:medicaments',
    'pharmacie:entree_stock',
    'pharmacie:sortie_stock',
    'pharmacie:fournisseurs',
    'pharmacie:mouvements',
]

PERMISSIONS_PHARMACIE = {
    'pharmacie.view', 'medicament.manage', 'stock.entree', 'stock.sortie',
}


@override_settings(ALLOWED_HOSTS=['testserver'])
class PharmacieReserveeAuPharmacienTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def connecter(self, role_code):
        utilisateur = User.objects.create_user(role_code, password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur, role=Role.objects.get(code=role_code))
        self.client.force_login(utilisateur)
        return utilisateur

    # --- la référence elle-même ---

    def test_la_reception_na_aucune_permission_de_pharmacie(self):
        accordees = set(ROLE_PERMISSIONS['receptionniste'])

        self.assertEqual(accordees & PERMISSIONS_PHARMACIE, set())

    def test_le_pharmacien_les_a_toutes(self):
        accordees = set(ROLE_PERMISSIONS['pharmacien'])

        self.assertEqual(PERMISSIONS_PHARMACIE - accordees, set())

    def test_la_reference_est_bien_appliquee_en_base(self):
        """installer_roles() remplace la liste, il ne l'enrichit pas."""
        role = Role.objects.get(code='receptionniste')

        en_base = set(role.permissions.values_list('code', flat=True))

        self.assertEqual(en_base & PERMISSIONS_PHARMACIE, set())

    # --- les pages, pour de vrai ---

    def test_la_reception_est_refusee_sur_toutes_les_pages_de_pharmacie(self):
        self.connecter('receptionniste')

        for nom in PAGES_PHARMACIE:
            with self.subTest(page=nom):
                reponse = self.client.get(reverse(nom))
                self.assertEqual(reponse.status_code, 302)

    def test_le_pharmacien_y_accede(self):
        self.connecter('pharmacien')

        for nom in PAGES_PHARMACIE:
            with self.subTest(page=nom):
                reponse = self.client.get(reverse(nom))
                self.assertEqual(reponse.status_code, 200)

    # --- le menu ---

    def test_le_menu_de_la_reception_ne_montre_pas_la_pharmacie(self):
        self.connecter('receptionniste')

        reponse = self.client.get(reverse('consultation:rdv_liste'))

        self.assertNotContains(reponse, reverse('pharmacie:medicaments'))
        self.assertNotContains(reponse, reverse('pharmacie:mouvements'))

    def test_le_menu_du_pharmacien_la_montre(self):
        self.connecter('pharmacien')

        reponse = self.client.get(reverse('pharmacie:medicaments'))

        self.assertContains(reponse, reverse('pharmacie:mouvements'))
