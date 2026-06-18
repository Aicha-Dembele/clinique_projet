"""Tests des rôles/permissions et du journal d'audit."""
from django.test import TestCase, override_settings
from django.contrib.auth.models import User

from comptes.models import Role, Profil, JournalAudit
from comptes.decorators import get_role


class GetRoleTests(TestCase):
    def test_superuser_est_admin(self):
        u = User.objects.create_superuser('boss', 'b@example.com', 'x')
        self.assertEqual(get_role(u), 'admin')

    def test_role_depuis_le_profil(self):
        role = Role.objects.create(code='medecin', libelle='Médecin')
        u = User.objects.create_user('doc', password='x')
        Profil.objects.create(user=u, role=role)
        self.assertEqual(get_role(u), 'medecin')

    def test_sans_profil_aucun_role(self):
        u = User.objects.create_user('inconnu', password='x')
        self.assertIsNone(get_role(u))


@override_settings(ALLOWED_HOSTS=['testserver'])
class ControleAccesTests(TestCase):
    """role_required protège les vues réservées : redirection si rôle insuffisant."""

    def test_non_admin_est_redirige(self):
        role = Role.objects.create(code='medecin', libelle='Médecin')
        u = User.objects.create_user('doc', password='secret')
        Profil.objects.create(user=u, role=role)
        self.client.force_login(u)
        r = self.client.get('/comptes/journal-audit/')
        self.assertEqual(r.status_code, 302)

    def test_admin_a_acces(self):
        u = User.objects.create_superuser('boss', 'b@example.com', 'secret')
        self.client.force_login(u)
        r = self.client.get('/comptes/journal-audit/')
        self.assertEqual(r.status_code, 200)


class JournalAuditTests(TestCase):
    def test_enregistrer_capture_le_contexte(self):
        from pharmacie.models import Medicament
        u = User.objects.create_user('agent', password='x')
        med = Medicament.objects.create(nom='Ibuprofène', quantite_stock=5)
        e = JournalAudit.enregistrer(u, 'suppression', med, details='test')
        self.assertEqual(e.action, 'suppression')
        self.assertEqual(e.modele, 'Medicament')
        self.assertEqual(e.objet_id, str(med.pk))
        self.assertEqual(e.user, u)

    def test_enregistrer_ignore_utilisateur_anonyme(self):
        from django.contrib.auth.models import AnonymousUser
        from pharmacie.models import Medicament
        med = Medicament.objects.create(nom='Aspirine', quantite_stock=5)
        e = JournalAudit.enregistrer(AnonymousUser(), 'creation', med)
        self.assertIsNone(e.user)
