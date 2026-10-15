"""Tests du planning du jour.

Deux lectures d'un même écran, et une frontière à ne pas franchir : la
réception doit voir QUI est attendu et QUAND, sans jamais atteindre le
dossier médical.
"""
from datetime import date, datetime, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Rendez_vous
from patients.models import Patient
from personnel.models import Medecin


@override_settings(ALLOWED_HOSTS=['testserver'])
class PlanningDuJourTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        self.jour = date(2026, 3, 10)

        self.house = Medecin.objects.create(
            nom='House', prenom='Gregory', telephone='1', service='Cardio',
            specialite='Cardiologie', role='medecin')
        self.cuddy = Medecin.objects.create(
            nom='Cuddy', prenom='Lisa', telephone='2', service='Derma',
            specialite='Dermatologie', role='medecin')

        self.keita = self.inscrire('Keita', 'Moussa', 'Masculin')
        self.diallo = self.inscrire('Diallo', 'Fanta', 'Feminin')

        self.rdv_matin = self.poser(self.house, self.keita, 9, 30)
        self.rdv_soir = self.poser(self.house, self.diallo, 16, 0)

    def inscrire(self, nom, prenom, sexe):
        """Un patient complet : tous ces champs sont obligatoires en base."""
        return Patient.objects.create(
            nom=nom, prenom=prenom, sexe=sexe,
            date_naissance=date(1990, 1, 1),
            adresse='Bamako', telephone='70000000',
            email=f'{prenom.lower()}@example.com', numero_urgence='70000001')

    def poser(self, medecin, patient, heure, minute, jour=None):
        """Un rendez-vous à une heure précise, dans le fuseau du projet."""
        naive = datetime.combine(jour or self.jour, datetime.min.time())
        naive = naive.replace(hour=heure, minute=minute)
        return Rendez_vous.objects.create(
            patient=patient, medecin=medecin,
            date=timezone.make_aware(naive))

    def connecter(self, role_code, medecin=None):
        utilisateur = User.objects.create_user(role_code, password='motdepasse-de-test')
        Profil.objects.create(user=utilisateur,
                              role=Role.objects.get(code=role_code),
                              medecin=medecin)
        self.client.force_login(utilisateur)
        return utilisateur

    def page(self, jour=None):
        return self.client.get(reverse('consultation:planning_jour'),
                               {'jour': (jour or self.jour).isoformat()})

    # --- ce que la réception voit ---

    def test_la_reception_voit_les_deux_medecins_cote_a_cote(self):
        self.connecter('receptionniste')

        reponse = self.page()

        self.assertEqual(reponse.status_code, 200)
        noms = [c['medecin'].nom for c in reponse.context['colonnes']]
        self.assertEqual(noms, ['Cuddy', 'House'])

    def test_la_charge_de_chaque_medecin_guide_le_choix(self):
        self.connecter('receptionniste')

        colonnes = {c['medecin'].nom: c['nb'] for c in self.page().context['colonnes']}

        # C'est ce compteur qui répond à « qui peut prendre ce patient ? ».
        self.assertEqual(colonnes['House'], 2)
        self.assertEqual(colonnes['Cuddy'], 0)

    def test_la_reception_voit_le_patient_et_lheure(self):
        self.connecter('receptionniste')

        reponse = self.page()

        self.assertContains(reponse, 'Keita')
        self.assertContains(reponse, '09:30')

    def test_la_reception_natteint_pas_le_dossier_medical(self):
        """La frontière : elle sait qui vient, pas pourquoi."""
        self.connecter('receptionniste')

        reponse = self.page()

        # Aucun lien a suivre depuis une case du planning.
        self.assertNotContains(
            reponse, reverse('patients:detail', args=[self.keita.pk]))
        # Et la porte reste fermee si elle tente l'adresse a la main.
        dossiers = self.client.get(reverse('consultation:dossiers'))
        self.assertEqual(dossiers.status_code, 302)

    # --- ce que le médecin voit ---

    def test_le_medecin_ne_voit_que_sa_propre_colonne(self):
        self.connecter('medecin', medecin=self.house)

        colonnes = self.page().context['colonnes']

        self.assertEqual(len(colonnes), 1)
        self.assertEqual(colonnes[0]['medecin'], self.house)

    def test_le_medecin_peut_ouvrir_le_patient_depuis_son_planning(self):
        self.connecter('medecin', medecin=self.house)

        reponse = self.page()

        self.assertContains(
            reponse, reverse('patients:detail', args=[self.keita.pk]))

    def test_un_medecin_sans_fiche_reliee_ne_voit_rien(self):
        """Le piège connu du projet : un profil médecin sans `profil.medecin`."""
        self.connecter('medecin', medecin=None)

        self.assertEqual(self.page().context['colonnes'], [])

    # --- le quadrillage des heures ---

    def test_les_heures_couvrent_la_journee_de_travail(self):
        self.connecter('receptionniste')

        heures = [l['heure'] for l in self.page().context['lignes']]

        self.assertEqual(heures[0], '08:00')
        self.assertEqual(heures[-1], '17:00')

    def test_un_rendez_vous_hors_horaires_elargit_le_tableau(self):
        """Un RDV a 19h52 ne doit disparaitre nulle part."""
        self.poser(self.cuddy, self.diallo, 19, 52)
        self.connecter('receptionniste')

        heures = [l['heure'] for l in self.page().context['lignes']]

        self.assertEqual(heures[-1], '19:00')

    def test_les_heures_creuses_hors_horaires_sont_sautees(self):
        """Un RDV a 01h18 ne doit pas trainer quinze lignes vides derriere lui."""
        self.poser(self.cuddy, self.diallo, 1, 18)
        self.connecter('receptionniste')

        lignes = self.page().context['lignes']
        heures = [l['heure'] for l in lignes]

        self.assertEqual(heures[0], '01:00')
        self.assertEqual(heures[1], '08:00')
        self.assertNotIn('03:00', heures)
        # Et la coupure est signalee, pour ne pas faire croire a une continuite.
        self.assertTrue(lignes[1]['apres_saut'])
        self.assertFalse(lignes[2]['apres_saut'])

    def test_chaque_rendez_vous_tombe_dans_la_bonne_case(self):
        self.connecter('receptionniste')

        lignes = {l['heure']: l for l in self.page().context['lignes']}

        case_9h = lignes['09:00']['cellules']
        occupee = [c for c in case_9h if c['rdvs']]
        self.assertEqual(len(occupee), 1)
        self.assertEqual(occupee[0]['medecin'], self.house)
        self.assertEqual(occupee[0]['rdvs'], [self.rdv_matin])

    # --- la navigation ---

    def test_un_autre_jour_na_pas_les_memes_rendez_vous(self):
        self.connecter('receptionniste')

        reponse = self.page(self.jour + timedelta(days=1))

        self.assertEqual(reponse.context['nb_rdv'], 0)
        self.assertNotContains(reponse, 'Keita')

    def test_une_date_illisible_ramene_a_aujourdhui(self):
        self.connecter('receptionniste')

        reponse = self.client.get(reverse('consultation:planning_jour'),
                                  {'jour': 'pas-une-date'})

        self.assertEqual(reponse.context['jour'], timezone.localdate())

    # --- le planning dans le formulaire de rendez-vous ---

    def test_le_formulaire_affiche_le_planning_du_jour(self):
        self.connecter('receptionniste')

        reponse = self.client.get(reverse('consultation:rdv_ajouter'),
                                  {'jour': self.jour.isoformat()})

        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Qui est disponible ce jour-là ?')
        self.assertContains(reponse, 'Keita')
        colonnes = {c['medecin'].nom: c['nb'] for c in reponse.context['colonnes']}
        self.assertEqual(colonnes, {'House': 2, 'Cuddy': 0})

    def test_le_formulaire_ne_propose_pas_un_second_nouveau_rendez_vous(self):
        """Le bouton du tableau n'a de sens que sur la page autonome."""
        self.connecter('receptionniste')

        reponse = self.client.get(reverse('consultation:rdv_ajouter'))

        self.assertNotContains(reponse, 'Nouveau rendez-vous')

    def test_changer_de_jour_ne_perd_pas_la_saisie(self):
        self.connecter('receptionniste')

        reponse = self.client.get(reverse('consultation:rdv_ajouter'), {
            'jour': self.jour.isoformat(),
            'patient': str(self.keita.pk),
            'medecin': str(self.cuddy.pk),
            'date': '2026-03-10T11:00',
        })

        saisi = reponse.context['saisi']
        self.assertEqual(saisi['patient'], str(self.keita.pk))
        self.assertEqual(saisi['medecin'], str(self.cuddy.pk))
        self.assertEqual(saisi['date'], '2026-03-10T11:00')

    def test_le_formulaire_de_modification_montre_le_jour_du_rendez_vous(self):
        self.connecter('receptionniste')

        reponse = self.client.get(
            reverse('consultation:rdv_modifier', args=[self.rdv_matin.pk]))

        self.assertEqual(reponse.context['jour'], self.jour)
        self.assertEqual(reponse.context['saisi']['patient'], str(self.keita.pk))

    def test_le_planning_du_formulaire_ne_mene_pas_au_dossier(self):
        """La meme frontiere qu'ailleurs, y compris ici."""
        self.connecter('receptionniste')

        reponse = self.client.get(reverse('consultation:rdv_ajouter'),
                                  {'jour': self.jour.isoformat()})

        self.assertNotContains(
            reponse, reverse('patients:detail', args=[self.keita.pk]))

    def test_un_rendez_vous_annule_ne_compte_pas_dans_la_charge(self):
        self.rdv_matin.statut = 'annule'
        self.rdv_matin.save()
        self.connecter('receptionniste')

        colonnes = {c['medecin'].nom: c['nb'] for c in self.page().context['colonnes']}

        self.assertEqual(colonnes['House'], 1)
