"""Ce qui doit rester lisible, ce que le médecin n'a pas besoin de voir, et les vrais chiffres."""
import re
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Consultation, ExamenMedical, Rendez_vous, ResultatExamen
from dashboard_view import repartition_types
from patients.models import Patient
from personnel.models import Medecin


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


class RepartitionDesExamensTests(SimpleTestCase):
    def test_les_parts_sont_reelles_du_plus_frequent_au_moins_frequent(self):
        parts = repartition_types(['Radio', 'Prise de sang', 'Prise de sang', 'Prise de sang'])
        self.assertEqual([(p['nom'], p['nb'], p['pct']) for p in parts],
                         [('Prise de sang', 3, 75), ('Radio', 1, 25)])

    def test_les_pourcentages_font_toujours_100(self):
        for types in (['A', 'B', 'C'], ['A', 'A', 'B', 'C', 'D', 'E', 'F'], ['A'] * 7 + ['B'] * 3 + ['C']):
            self.assertEqual(sum(p['pct'] for p in repartition_types(types)), 100, types)

    def test_au_dela_de_quatre_types_le_reste_va_dans_autres(self):
        parts = repartition_types(['A', 'A', 'B', 'B', 'C', 'C', 'D', 'D', 'E', 'F'])
        self.assertEqual([p['nom'] for p in parts], ['A', 'B', 'C', 'D', 'Autres'])
        self.assertEqual(parts[-1]['nb'], 2)
        self.assertEqual(len({p['couleur'] for p in parts}), 5)

    def test_les_majuscules_et_les_espaces_ne_font_pas_deux_types(self):
        parts = repartition_types(['Prise de sang', ' prise de sang '])
        self.assertEqual([(p['nom'], p['pct']) for p in parts], [('Prise de sang', 100)])

    def test_sans_examen_il_n_y_a_rien_a_repartir(self):
        self.assertEqual(repartition_types([]), [])


@override_settings(ALLOWED_HOSTS=['testserver'])
class ChiffresReelsTests(TestCase):
    """Un chiffre affiché doit venir des données : « Sur quoi tu te bases ? »."""

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def connecter(self, nom, role):
        user = User.objects.create_user(nom, password='motdepasse-de-test')
        Profil.objects.create(user=user, role=Role.objects.get(code=role))
        self.client.force_login(user)

    def examen(self, type_examen, jour=None):
        patient = Patient.objects.create(
            nom='Keita', prenom='Moussa', sexe='Masculin', date_naissance=date(1990, 1, 1),
            adresse='Bamako', telephone='70000000', email='k@example.com', numero_urgence='70000001')
        medecin = Medecin.objects.create(nom='House', prenom='G', telephone='1', service='Diag',
                                         specialite='Généraliste', role='medecin')
        rdv = Rendez_vous.objects.create(patient=patient, medecin=medecin, date=timezone.now(),
                                         statut='programme')
        consultation = Consultation.objects.create(rendez_vous=rdv, motif='Toux')
        return ExamenMedical.objects.create(
            patient=patient, consultation=consultation, medecin=medecin,
            type_examen=type_examen, date=jour or timezone.localdate())

    def test_le_laborantin_voit_les_vrais_types_d_examens(self):
        self.examen('Prise de sang')
        self.examen('Prise de sang')
        self.examen('Scanner')
        self.connecter('labo', 'laborantin')
        page = self.client.get(reverse('dashboard'))
        self.assertEqual([(t['nom'], t['pct']) for t in page.context['types_analyses']],
                         [('Prise de sang', 67), ('Scanner', 33)])
        self.assertContains(page, '67%')
        for inventee in ('Hématologie', 'Biochimie', 'Bactério', '38%'):
            self.assertNotContains(page, inventee)

    def test_sans_examen_le_laborantin_ne_voit_pas_de_faux_graphique(self):
        self.connecter('labo', 'laborantin')
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, 'Aucun examen enregistré')
        self.assertNotContains(page, 'id="typesChart"')

    def test_ce_mois_et_aujourd_hui_comptent_vraiment_ce_mois_et_aujourd_hui(self):
        self.examen('Scanner', jour=timezone.localdate() - timedelta(days=400))
        recent = self.examen('Scanner')
        ResultatExamen.objects.create(patient=recent.patient, examen=recent, resultat='Normal')
        self.connecter('labo', 'laborantin')
        contexte = self.client.get(reverse('dashboard')).context
        self.assertEqual(contexte['total_examens_mois'], 1)
        self.assertEqual(contexte['total_examens'], 2)
        self.assertEqual(contexte['resultats_du_jour'], 1)

    def test_les_rapports_montrent_les_modes_de_paiement_qui_existent(self):
        self.connecter('chef', 'admin')
        page = self.client.get(reverse('facturation:rapports'))
        self.assertContains(page, 'SAMA Money')
        self.assertNotContains(page, 'Orange Money')
        self.assertNotContains(page, 'Carte bancaire')

    def test_la_page_du_personnel_n_invente_plus_de_chiffres(self):
        self.connecter('chef', 'admin')
        page = self.client.get(reverse('personnel:liste'))
        self.assertEqual(page.status_code, 200)
        for inventee in ('68%', 'Tous actifs', 'ce mois', 'Cette semaine'):
            self.assertNotContains(page, inventee)
