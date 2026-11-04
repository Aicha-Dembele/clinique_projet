"""Le petit dessin et la jauge de stock affichés dans les listes de médicaments."""
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

from pharmacie.models import Medicament


class DessinTests(SimpleTestCase):
    def test_la_forme_choisit_le_dessin_sans_tenir_compte_de_la_casse_ni_des_accents(self):
        cas = {
            'Comprimé': 'comprime', 'comprimé': 'comprime', 'GÉLULE': 'gelule',
            'Aérosol': 'aerosol', 'sirop': 'flacon', 'rouleau': 'bande',
        }
        for forme, dessin in cas.items():
            self.assertEqual(Medicament(forme=forme).dessin(), dessin, forme)

    def test_une_solution_injectable_est_une_ampoule_pas_un_flacon(self):
        self.assertEqual(Medicament(forme='Solution injectable').dessin(), 'ampoule')

    def test_sans_forme_connue_la_categorie_decide(self):
        self.assertEqual(Medicament(forme='', categorie='solute').dessin(), 'poche')
        self.assertEqual(Medicament(forme='', categorie='consommable').dessin(), 'pansement')
        self.assertEqual(Medicament(forme='', categorie='antibiotique').dessin(), 'plaquette')
        self.assertEqual(Medicament(forme='truc inconnu').dessin(), 'plaquette')

    def test_chaque_dessin_a_son_fichier_et_sa_classe(self):
        """Une classe ou un fichier manquant ne ferait aucune erreur : juste un rond vide."""
        feuille = Path(finders.find('consultation/css/theme_nevroglie.css')).read_text(encoding='utf-8')
        dessins = {d for _, d in Medicament.DESSINS_FORME} | {'plaquette', 'poche', 'pansement'}
        for dessin in dessins:
            self.assertTrue(finders.find(f'consultation/img/motifs/icone_{dessin}.svg'), dessin)
            self.assertIn(f'.dessin-{dessin} ', feuille)


class JaugeStockTests(SimpleTestCase):
    def jauge(self, stock, seuil):
        return Medicament(quantite_stock=stock, seuil_alerte=seuil).jauge_stock()

    def test_vide_en_rupture(self):
        self.assertEqual(self.jauge(0, 10), 0)

    def test_le_seuil_tombe_au_tiers_de_la_jauge(self):
        self.assertEqual(self.jauge(10, 10), 33)

    def test_pleine_a_trois_fois_le_seuil_et_jamais_au_dela(self):
        self.assertEqual(self.jauge(30, 10), 100)
        self.assertEqual(self.jauge(500, 10), 100)

    def test_sans_seuil_elle_est_pleine_des_qu_il_reste_du_stock(self):
        self.assertEqual(self.jauge(3, 0), 100)
