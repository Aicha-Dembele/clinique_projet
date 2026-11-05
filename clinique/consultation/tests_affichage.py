"""Ce qui doit rester lisible, et ce que le médecin n'a pas besoin de voir."""
import re

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from comptes.models import Profil, Role
from comptes.roles import installer_roles


class PagesSansVerreTests(SimpleTestCase):
    """Le style « en verre » (texte blanc, cartes translucides) allait avec les anciens fonds
    photo. Sur le fond clair d'aujourd'hui, il rend une page presque invisible."""

    MOTIFS = (
        re.compile(r'\.form-section\s*\{[^}]*rgba\(255,\s*255,\s*255'),
        re.compile(r'body\.page-[a-z]+-bg[^{}]*\{[^}]*background[^;}]*rgba\(255,\s*255,\s*255'),
    )

    def test_aucun_gabarit_ne_garde_ce_style(self):
        for gabarit in (settings.BASE_DIR / 'templates').rglob('*.html'):
            contenu = gabarit.read_text(encoding='utf-8')
            for motif in self.MOTIFS:
                self.assertIsNone(motif.search(contenu), f'{gabarit.name} : {motif.pattern}')


@override_settings(ALLOWED_HOSTS=['testserver'])
class RappelDePaiementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def test_le_medecin_ne_voit_pas_le_rappel_de_paiement(self):
        """S'il reçoit le patient, c'est que le patient a payé : cela ne le regarde pas."""
        medecin = User.objects.create_user('dr_house', password='motdepasse-de-test')
        Profil.objects.create(user=medecin, role=Role.objects.get(code='medecin'))
        self.client.force_login(medecin)
        page = self.client.get(reverse('consultation:ajouter'))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "se règle d'avance")
        self.assertNotContains(page, 'avis-paiement')
        self.assertContains(page, 'name="rendez_vous"')
