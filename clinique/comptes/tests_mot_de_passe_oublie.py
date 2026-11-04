"""« Mot de passe oublié » : chaque personne reçoit le lien à sa propre adresse."""
import re

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from comptes.models import Profil, Role

ANCIEN = 'Ancien-mot-de-passe-2026'
NOUVEAU = 'Nouveau-mot-de-passe-2026'


def destinataires():
    return [m.to for m in mail.outbox]


class DemandeDeLienTests(TestCase):
    def setUp(self):
        self.aminata = User.objects.create_user('aminata', 'aminata@exemple.ml', ANCIEN)
        self.binta = User.objects.create_user('binta', 'binta@exemple.ml', ANCIEN)

    def _demander(self, adresse):
        return self.client.post(reverse('password_reset'), {'email': adresse})

    def test_chaque_personne_recoit_le_lien_a_sa_propre_adresse(self):
        for compte in (self.aminata, self.binta):
            mail.outbox.clear()
            self._demander(compte.email)
            self.assertEqual(destinataires(), [[compte.email]])

    def test_les_majuscules_tapees_ne_changent_rien(self):
        """Sur MySQL en utf8mb4_bin, le formulaire d'origine de Django ne trouvait personne."""
        for saisie in ('AMINATA@EXEMPLE.ML', 'Aminata@exemple.ml'):
            mail.outbox.clear()
            self._demander(saisie)
            self.assertEqual(destinataires(), [['aminata@exemple.ml']])

    def test_les_majuscules_enregistrees_ne_changent_rien(self):
        User.objects.filter(pk=self.binta.pk).update(email='Binta@Exemple.ml')
        self._demander('binta@exemple.ml')
        self.assertEqual(destinataires(), [['Binta@Exemple.ml']])

    def test_une_adresse_qui_ressemble_ne_recoit_pas_le_lien(self):
        """« ı » sans point : c'est une autre adresse, pas celle du compte."""
        self._demander('amınata@exemple.ml')
        self.assertEqual(mail.outbox, [])

    def test_une_adresse_inconnue_n_envoie_rien_et_ne_le_dit_pas(self):
        """Sinon n'importe qui pourrait tester quelles adresses ont un compte à la clinique."""
        connue = self._demander('aminata@exemple.ml')
        inconnue = self._demander('personne@exemple.ml')
        self.assertEqual(destinataires(), [['aminata@exemple.ml']])
        self.assertEqual(inconnue.status_code, 302)
        self.assertEqual(inconnue.url, connue.url)

    def test_un_compte_desactive_ne_recoit_rien(self):
        User.objects.filter(pk=self.aminata.pk).update(is_active=False)
        self._demander('aminata@exemple.ml')
        self.assertEqual(mail.outbox, [])

    def test_deux_comptes_sur_la_meme_adresse_recoivent_chacun_leur_lien(self):
        """L'email nomme le compte : c'est ce qui permet de choisir le bon lien."""
        User.objects.filter(pk=self.binta.pk).update(email=self.aminata.email)
        self._demander(self.aminata.email)
        self.assertEqual(len(mail.outbox), 2)
        corps = ' '.join(m.body for m in mail.outbox)
        self.assertIn("Votre nom d'utilisateur : aminata", corps)
        self.assertIn("Votre nom d'utilisateur : binta", corps)

    def test_le_lien_recu_permet_de_changer_le_mot_de_passe(self):
        self._demander('AMINATA@exemple.ml')
        lien = re.search(r'http://testserver(/reset/\S+)', mail.outbox[0].body).group(1)

        page = self.client.get(lien, follow=True)
        self.assertContains(page, 'Nouveau mot de passe')
        fin = self.client.post(page.redirect_chain[-1][0], {
            'new_password1': NOUVEAU, 'new_password2': NOUVEAU})
        self.assertRedirects(fin, reverse('password_reset_complete'))
        self.assertTrue(self.client.login(username='aminata', password=NOUVEAU))
        self.assertFalse(self.client.login(username='aminata', password=ANCIEN))

        # Le lien ne sert qu'une fois.
        self.client.logout()
        self.assertContains(self.client.get(lien, follow=True), 'Lien invalide')


class EmailObligatoireTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('chef', 'chef@exemple.ml', ANCIEN))
        self.role, _ = Role.objects.get_or_create(code='infirmier', defaults={'libelle': 'Infirmier'})

    def _ajouter(self, email):
        return self.client.post(reverse('comptes:utilisateur_ajouter'), {
            'username': 'nouvelle', 'password': ANCIEN, 'role': self.role.pk, 'email': email})

    def _modifier(self, profil, email):
        return self.client.post(reverse('comptes:utilisateur_modifier', args=[profil.pk]), {
            'username': profil.user.username, 'role': self.role.pk, 'is_active': 'on', 'email': email})

    def test_on_ne_cree_pas_de_compte_sans_vraie_adresse(self):
        for email in ('', '   ', 'pas-une-adresse', 'aminata@exemple'):
            self._ajouter(email)
            self.assertFalse(User.objects.filter(username='nouvelle').exists(), email)

    def test_un_compte_avec_une_adresse_est_cree(self):
        self._ajouter(' nouvelle@exemple.ml ')
        self.assertEqual(User.objects.get(username='nouvelle').email, 'nouvelle@exemple.ml')

    def test_on_ne_peut_pas_vider_l_adresse_d_un_compte(self):
        user = User.objects.create_user('aminata', 'aminata@exemple.ml', ANCIEN)
        profil = Profil.objects.create(user=user, role=self.role)
        reponse = self._modifier(profil, '')
        self.assertRedirects(reponse, reverse('comptes:utilisateur_modifier', args=[profil.pk]))
        user.refresh_from_db()
        self.assertEqual(user.email, 'aminata@exemple.ml')

    def test_corriger_l_adresse_fait_marcher_le_mot_de_passe_oublie(self):
        """Le vrai cas : le compte porte une adresse inventée, la personne tape la sienne."""
        user = User.objects.create_user('aminata', 'inventee@exemple.ml', ANCIEN)
        profil = Profil.objects.create(user=user, role=self.role)

        self.client.post(reverse('password_reset'), {'email': 'aminata@exemple.ml'})
        self.assertEqual(mail.outbox, [])

        self._modifier(profil, 'aminata@exemple.ml')
        self.client.post(reverse('password_reset'), {'email': 'aminata@exemple.ml'})
        self.assertEqual(destinataires(), [['aminata@exemple.ml']])

    def test_la_liste_signale_les_comptes_sans_adresse(self):
        sans = Profil.objects.create(user=User.objects.create_user('sans', '', ANCIEN), role=self.role)
        page = self.client.get(reverse('comptes:utilisateurs_liste'))
        self.assertContains(page, 'Aucun email', count=1)
        sans.user.email = 'sans@exemple.ml'
        sans.user.save()
        page = self.client.get(reverse('comptes:utilisateurs_liste'))
        self.assertNotContains(page, 'Aucun email')
