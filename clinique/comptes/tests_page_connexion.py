"""La page de connexion : son apparence a changé, son fonctionnement ne doit pas bouger."""
import re

from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from comptes.models import Profil, Role
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


class PageExpireeTests(TestCase):
    """Un formulaire refusé par la protection CSRF : un message compréhensible, et toujours aucun envoi accepté."""

    def setUp(self):
        # Le client de test ignore cette protection, sauf si on lui demande de l'appliquer.
        self.navigateur = self.client_class(enforce_csrf_checks=True)
        self.url = reverse('login')
        self.identifiants = {'username': 'aminata', 'password': 'bon-mot-de-passe'}
        self.user = User.objects.create_user('aminata', 'aminata@exemple.ml', self.identifiants['password'])

    def test_un_envoi_sans_jeton_affiche_un_message_clair(self):
        page = self.navigateur.post(self.url, self.identifiants)
        self.assertContains(page, 'Cette page a expiré', status_code=403)
        self.assertContains(page, f'href="{self.url}"', status_code=403)
        self.assertNotContains(page, 'CSRF', status_code=403)

    def test_un_jeton_perime_affiche_le_meme_message(self):
        self.navigateur.get(self.url)
        page = self.navigateur.post(self.url, {**self.identifiants, 'csrfmiddlewaretoken': 'perime'})
        self.assertContains(page, 'Cette page a expiré', status_code=403)

    def test_la_protection_refuse_toujours_la_connexion(self):
        self.navigateur.post(self.url, self.identifiants)
        self.assertIsNone(self.navigateur.session.get('_auth_user_id'))

    def test_apres_le_message_on_peut_se_connecter(self):
        self.navigateur.post(self.url, self.identifiants)
        html = self.navigateur.get(self.url).content.decode()
        jeton = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
        reponse = self.navigateur.post(self.url, {**self.identifiants, 'csrfmiddlewaretoken': jeton})
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(self.navigateur.session.get('_auth_user_id'), str(self.user.pk))

    def test_pour_une_personne_connectee_rien_n_est_enregistre_et_continuer_mene_a_l_accueil(self):
        """Le message annonce que rien n'est enregistré : il faut que ce soit vrai."""
        role, _ = Role.objects.get_or_create(code='infirmier', defaults={'libelle': 'Infirmier'})
        Profil.objects.create(user=self.user, role=role)
        self.navigateur.force_login(self.user)
        page = self.navigateur.post(reverse('comptes:mon_profil'), {
            'email': 'autre@exemple.ml', 'mot_de_passe': self.identifiants['password']})
        self.assertContains(page, "n'a pas été enregistré", status_code=403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'aminata@exemple.ml')
        self.assertRedirects(self.navigateur.get(self.url), reverse('dashboard'), fetch_redirect_response=False)


class BarreDuHautTests(TestCase):
    def test_le_nom_de_la_clinique_reste_dans_le_menu(self):
        """Sur téléphone, le nom n'apparaît qu'une fois le menu ouvert : à côté des trois traits, il dépassait."""
        self.client.force_login(User.objects.create_superuser('chef', 'chef@exemple.ml', 'x'))
        html = self.client.get(reverse('dashboard')).content.decode()
        barre = html.split('<div class="tb-brand">')[1].split('</div>')[0]
        self.assertEqual(re.sub(r'<[^>]+>', '', barre).strip(), '')
        self.assertIn('<div class="sb-name">Nevroglie</div>', html)
