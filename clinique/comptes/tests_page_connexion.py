"""La page de connexion : son apparence a changé, son fonctionnement ne doit pas bouger."""
import re

from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from comptes.views import REMEMBER_COOKIE


class PageConnexionTests(TestCase):
    def setUp(self):
        self.url = reverse('login')

    def test_le_formulaire_a_tout_ce_qu_il_faut(self):
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        for attendu in ('name="username"', 'name="password"', 'name="remember"', 'csrfmiddlewaretoken'):
            self.assertContains(page, attendu)
        self.assertContains(page, reverse('password_reset'))

    def test_chaque_photo_de_la_page_existe(self):
        """Une photo manquante ne ferait aucune erreur : juste un rond vide."""
        html = self.client.get(self.url).content.decode()
        photos = set(re.findall(r'consultation/img/[\w.]+', html))
        self.assertGreaterEqual(len(photos), 6)
        for photo in photos:
            self.assertTrue(finders.find(photo), photo)

    def test_chaque_portrait_a_aussi_sa_place_sur_telephone(self):
        """Sans --tx et --ty, tous les portraits s'empileraient dans un coin de l'écran."""
        html = self.client.get(self.url).content.decode()
        elements = re.findall(r'class="(?:portrait|puce)" style="([^"]+)"', html)
        self.assertEqual(len(elements), 16)
        for style in elements:
            for variable in ('--tx:', '--ty:', '--tt:'):
                self.assertIn(variable, style)

    def test_un_mauvais_mot_de_passe_affiche_l_erreur(self):
        User.objects.create_user('aminata', password='bon-mot-de-passe')
        page = self.client.post(self.url, {'username': 'aminata', 'password': 'mauvais'})
        self.assertContains(page, 'mot de passe incorrect')
        self.assertContains(page, 'value="aminata"')

    def test_le_bon_mot_de_passe_connecte_et_quitte_la_page(self):
        User.objects.create_user('aminata', password='bon-mot-de-passe')
        page = self.client.post(self.url, {'username': 'aminata', 'password': 'bon-mot-de-passe'})
        self.assertEqual(page.status_code, 302)
        self.assertEqual(self.client.session.get('_auth_user_id'), str(User.objects.get(username='aminata').pk))

    def test_se_souvenir_de_moi_preremplit_le_nom_a_la_visite_suivante(self):
        User.objects.create_user('aminata', password='bon-mot-de-passe')
        reponse = self.client.post(self.url, {'username': 'aminata', 'password': 'bon-mot-de-passe', 'remember': 'on'})
        # Un navigateur neuf qui n'a que ce cookie : client.logout() les effacerait tous.
        visiteur = self.client_class()
        visiteur.cookies[REMEMBER_COOKIE] = reponse.cookies[REMEMBER_COOKIE].value
        page = visiteur.get(self.url)
        self.assertContains(page, 'value="aminata"')
        self.assertContains(page, 'checked')


class BarreDuHautTests(TestCase):
    def test_le_nom_de_la_clinique_reste_dans_le_menu(self):
        """Sur téléphone, le nom n'apparaît qu'une fois le menu ouvert : à côté des trois traits, il dépassait."""
        self.client.force_login(User.objects.create_superuser('chef', 'chef@exemple.ml', 'x'))
        html = self.client.get(reverse('dashboard')).content.decode()
        barre = html.split('<div class="tb-brand">')[1].split('</div>')[0]
        self.assertEqual(re.sub(r'<[^>]+>', '', barre).strip(), '')
        self.assertIn('<div class="sb-name">Nevroglie</div>', html)
