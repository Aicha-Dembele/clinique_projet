"""Les cartes de montants : un chiffre ne doit jamais sortir de sa carte.

La mesure se fait dans le navigateur (ajusterChiffres, dans base.html) : ces tests
vérifient que les pages gardent ce qu'il faut pour cela. Un montant coupé se lirait
comme un autre montant : 1 250 000 deviendrait 1 250.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class CartesDeMontantsTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('chef', 'chef@exemple.ml', 'x'))

    def test_les_pages_de_montants_laissent_toute_la_largeur_au_chiffre(self):
        for nom in ('facturation:liste', 'facturation:paiements', 'facturation:creances'):
            html = self.client.get(reverse(nom)).content.decode()
            self.assertIn('stats-montants', html, nom)
            # Sans ce bloc, le libellé et le chiffre ne se placent pas dans la grille de la carte.
            self.assertEqual(html.count('class="stat-h-val"'), html.count('class="stat-h-info"'), nom)

    def test_l_unite_des_paiements_passe_sous_le_montant(self):
        html = self.client.get(reverse('facturation:paiements')).content.decode()
        self.assertRegex(html, r'class="stat-h-val">0 <small[^>]*>FCFA</small>')

    def test_chaque_page_ajuste_ses_chiffres(self):
        self.assertContains(self.client.get(reverse('dashboard')), 'function ajusterChiffres')
