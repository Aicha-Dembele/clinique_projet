"""La recherche des listes : par début de mot, sans tenir compte des majuscules ni des accents.

Le bug d'origine : sur la base MySQL de la clinique (collation utf8mb4_bin,
qui distingue les majuscules), taper « oumar kante » ne trouvait pas le
patient Kante Oumar. Ces tests tournent aussi bien sur SQLite que sur MySQL.
"""
from datetime import date

from django.test import TestCase

from comptes.recherche import normaliser, termes_q
from patients.models import Patient


def _patient(nom, prenom, telephone='70000000'):
    return Patient.objects.create(
        nom=nom, prenom=prenom, sexe='Masculin', date_naissance=date(1990, 1, 1),
        adresse='Bamako', telephone=telephone, email='x@example.com', numero_urgence='1')


class RechercheTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.kante = _patient('Kante', 'Oumar')
        cls.traore = _patient('TRAORÉ', 'Awa', telephone='+223 70 00 00 21')
        cls.konate = _patient('Konaté', 'Moussa')
        cls.diakite = _patient('Diakité', 'Jean-Pierre')

    def trouver(self, q, *champs):
        champs = champs or ('nom', 'prenom')
        return set(Patient.objects.filter(termes_q(q, *champs)).values_list('pk', flat=True))

    def test_les_majuscules_ne_comptent_pas(self):
        for terme in ['kante', 'KANTE', 'Kante', 'kAnTe']:
            with self.subTest(terme=terme):
                self.assertEqual(self.trouver(terme), {self.kante.pk})

    def test_les_accents_ne_comptent_pas(self):
        self.assertEqual(self.trouver('traore'), {self.traore.pk})
        self.assertEqual(self.trouver('kanté'), {self.kante.pk})
        self.assertEqual(self.trouver('konate'), {self.konate.pk})

    def test_le_nom_complet_dans_les_deux_sens(self):
        for terme in ['Oumar Kante', 'oumar kante', 'kante oumar']:
            with self.subTest(terme=terme):
                self.assertEqual(self.trouver(terme), {self.kante.pk})

    def test_chaque_lettre_affine_la_liste(self):
        """K → Ka → Kan : les noms qui COMMENCENT par ces lettres."""
        self.assertEqual(self.trouver('k'), {self.kante.pk, self.konate.pk})
        self.assertEqual(self.trouver('ka'), {self.kante.pk})
        self.assertEqual(self.trouver('kan'), {self.kante.pk})

    def test_le_milieu_dun_mot_ne_compte_pas(self):
        """« ante » est dans Kante, mais aucun mot ne commence par « ante »."""
        self.assertEqual(self.trouver('ante'), set())
        # « k » ne remonte pas Diakité : le k y est au milieu du mot.
        self.assertNotIn(self.diakite.pk, self.trouver('k'))

    def test_un_prenom_compose(self):
        self.assertEqual(self.trouver('pierre'), {self.diakite.pk})

    def test_un_numero_de_telephone(self):
        self.assertEqual(self.trouver('70 00 00 21', 'telephone'), {self.traore.pk})

    def test_une_recherche_vide_ne_filtre_rien(self):
        self.assertEqual(len(self.trouver('   ')), 4)

    def test_normaliser(self):
        self.assertEqual(normaliser("KÉÏDA N'Diaye-Coulibaly"), 'keida n diaye coulibaly')

    def test_par_le_numero_affiche_dans_la_liste(self):
        """« P-0003 », « p3 » ou « 3 » : le numéro tel qu'il apparaît dans la liste."""
        pk = self.konate.pk
        for terme in [f'P-{pk:04d}', f'p{pk}', str(pk), f'P {pk}']:
            with self.subTest(terme=terme):
                trouves = set(Patient.objects.filter(
                    termes_q(terme, 'nom', 'prenom', numero='P')).values_list('pk', flat=True))
                self.assertIn(pk, trouves)

    def test_un_mot_ordinaire_nest_pas_pris_pour_un_numero(self):
        trouves = set(Patient.objects.filter(
            termes_q('kante', 'nom', 'prenom', numero='P')).values_list('pk', flat=True))
        self.assertEqual(trouves, {self.kante.pk})


class SansCasseTests(TestCase):
    """Les comparaisons « sans majuscules » qui étaient fausses sur MySQL utf8mb4_bin.

    Sur cette collation, __iexact et __istartswith distinguent les majuscules :
    les compteurs Hommes/Femmes affichaient 0, et toutes les chambres étaient
    facturées au premier tarif trouvé (celui de l'urgence). Ces tests ne
    peuvent échouer que sur MySQL ; sur SQLite ils vérifient le comportement.
    """

    def test_le_prix_de_la_nuit_suit_le_type_de_chambre(self):
        from decimal import Decimal

        from consultation.models import Hospitalisation
        from facturation.models import Tarif

        for specialite, prix in [('Urgence', 20000), ('Simple', 10000), ('Double', 15000), ('VIP', 25000)]:
            Tarif.objects.create(type_service='hospitalisation', specialite=specialite,
                                 nom='Hospitalisation', prix=Decimal(prix))
        for type_chambre, prix in [('vip', 25000), ('double', 15000), ('simple', 10000), ('urgence', 20000)]:
            with self.subTest(type=type_chambre):
                self.assertEqual(Hospitalisation(type_chambre=type_chambre).get_prix_nuit(), Decimal(prix))

    def test_les_compteurs_hommes_et_femmes(self):
        from django.contrib.auth.models import User
        from django.test import override_settings

        _patient('Kante', 'Oumar')                                   # sexe « Masculin »
        Patient.objects.filter(pk=_patient('Traoré', 'Awa').pk).update(sexe='Féminin')
        self.client.force_login(User.objects.create_superuser('boss', 'b@b.c', 'x'))
        with override_settings(ALLOWED_HOSTS=['testserver']):
            r = self.client.get('/patients/')
        self.assertEqual((r.context['nb_hommes'], r.context['nb_femmes']), (1, 1))
