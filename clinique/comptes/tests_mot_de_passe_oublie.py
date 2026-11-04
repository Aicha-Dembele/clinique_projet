"""« Mot de passe oublié » : chaque personne reçoit le lien à sa propre adresse."""
import re

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from comptes.models import JournalAudit, Profil, Role

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


class EmailDansMonProfilTests(TestCase):
    """Chaque personne corrige sa propre adresse, à condition de redonner son mot de passe."""

    def setUp(self):
        role, _ = Role.objects.get_or_create(code='infirmier', defaults={'libelle': 'Infirmier'})
        self.user = User.objects.create_user('aminata', 'inventee@exemple.ml', ANCIEN)
        Profil.objects.create(user=self.user, role=role)
        self.client.force_login(self.user)
        self.url = reverse('comptes:mon_profil')

    def _changer(self, email, mot_de_passe=ANCIEN, **autres):
        return self.client.post(self.url, {'email': email, 'mot_de_passe': mot_de_passe, **autres})

    def _adresse(self):
        self.user.refresh_from_db()
        return self.user.email

    def test_la_page_propose_l_adresse_actuelle(self):
        page = self.client.get(self.url)
        self.assertContains(page, 'value="inventee@exemple.ml"')
        self.assertContains(page, 'name="mot_de_passe"')
        self.assertContains(page, 'csrfmiddlewaretoken')
        self.assertNotContains(page, 'Aucune adresse')

    def test_un_compte_sans_adresse_est_prevenu(self):
        User.objects.filter(pk=self.user.pk).update(email='')
        self.assertContains(self.client.get(self.url), 'Aucune adresse')

    def test_le_bon_mot_de_passe_change_l_adresse(self):
        reponse = self._changer(' aminata@exemple.ml ')
        # Sans fetch_redirect_response=False, cette vérification lirait la page et consommerait le message.
        self.assertRedirects(reponse, self.url, fetch_redirect_response=False)
        self.assertEqual(self._adresse(), 'aminata@exemple.ml')
        # L'adresse est réaffichée pour qu'on puisse repérer une faute de frappe.
        self.assertContains(self.client.get(self.url), 'Adresse enregistrée : aminata@exemple.ml')

    def test_on_reste_connecte_apres_le_changement(self):
        self._changer('aminata@exemple.ml')
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_sans_le_bon_mot_de_passe_rien_ne_change(self):
        for mot_de_passe in ('', 'mauvais'):
            page = self._changer('aminata@exemple.ml', mot_de_passe)
            self.assertContains(page, 'Mot de passe incorrect')
            self.assertEqual(self._adresse(), 'inventee@exemple.ml')

    def test_apres_une_erreur_l_adresse_tapee_reste_mais_pas_le_mot_de_passe(self):
        page = self._changer('aminata@exemple.ml', 'mauvais')
        self.assertContains(page, 'value="aminata@exemple.ml"')
        self.assertNotContains(page, 'mauvais')

    def test_une_fausse_adresse_est_refusee(self):
        trop_longue = 'a' * 250 + '@exemple.ml'
        for email in ('', '   ', 'pas-une-adresse', 'aminata@exemple', trop_longue):
            page = self._changer(email)
            self.assertEqual(page.status_code, 200, email)
            self.assertEqual(self._adresse(), 'inventee@exemple.ml', email)

    def test_on_ne_touche_a_rien_d_autre_ni_a_personne_d_autre(self):
        """Le formulaire ne doit servir ni à changer de rôle, ni à viser le compte de quelqu'un."""
        autre = User.objects.create_user('binta', 'binta@exemple.ml', ANCIEN)
        self._changer('aminata@exemple.ml', username='chef', first_name='Chef', is_staff='on',
                      is_superuser='on', pk=autre.pk, user=autre.pk, id=autre.pk)
        self.user.refresh_from_db()
        autre.refresh_from_db()
        self.assertEqual(self.user.email, 'aminata@exemple.ml')
        self.assertEqual((self.user.username, self.user.first_name), ('aminata', ''))
        self.assertFalse(self.user.is_staff or self.user.is_superuser)
        self.assertEqual(autre.email, 'binta@exemple.ml')

    def test_il_faut_etre_connecte(self):
        self.client.logout()
        reponse = self._changer('aminata@exemple.ml')
        self.assertEqual(reponse.status_code, 302)
        self.assertIn(reverse('login'), reponse.url)
        self.assertEqual(self._adresse(), 'inventee@exemple.ml')

    def test_un_compte_sans_profil_peut_aussi_corriger_son_adresse(self):
        """Des comptes anciens n'ont pas de profil : la page d'administration ne les liste pas."""
        sans_profil = User.objects.create_superuser('ancien', '', ANCIEN)
        self.client.force_login(sans_profil)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self._changer('ancien@exemple.ml')
        sans_profil.refresh_from_db()
        self.assertEqual(sans_profil.email, 'ancien@exemple.ml')

    def test_le_lien_part_vers_la_nouvelle_adresse_et_plus_vers_l_ancienne(self):
        self._changer('aminata@exemple.ml')
        self.client.logout()
        self.client.post(reverse('password_reset'), {'email': 'inventee@exemple.ml'})
        self.assertEqual(mail.outbox, [])
        self.client.post(reverse('password_reset'), {'email': 'aminata@exemple.ml'})
        self.assertEqual(destinataires(), [['aminata@exemple.ml']])

    def test_un_lien_deja_envoye_a_l_ancienne_adresse_ne_marche_plus(self):
        self.client.post(reverse('password_reset'), {'email': 'inventee@exemple.ml'})
        lien = re.search(r'http://testserver(/reset/\S+)', mail.outbox[0].body).group(1)
        self._changer('aminata@exemple.ml')
        self.client.logout()
        self.assertContains(self.client.get(lien, follow=True), 'Lien invalide')

    def test_le_changement_est_note_au_journal_sans_le_mot_de_passe(self):
        self._changer('aminata@exemple.ml')
        entree = JournalAudit.objects.get(modele='User', objet_id=str(self.user.pk))
        self.assertEqual(entree.user, self.user)
        self.assertEqual(entree.action, 'modification')
        self.assertIn('inventee@exemple.ml', entree.details)
        self.assertIn('aminata@exemple.ml', entree.details)
        self.assertNotIn(ANCIEN, entree.details)

    def test_rien_n_est_note_quand_rien_ne_change(self):
        self._changer('inventee@exemple.ml')
        self._changer('aminata@exemple.ml', 'mauvais')
        self.assertFalse(JournalAudit.objects.filter(modele='User').exists())
