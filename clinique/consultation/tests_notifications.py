"""Notifications : chacun reçoit ce qui le concerne, et seulement ce qui le concerne."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comptes.models import Notification, Profil, Role
from comptes.roles import installer_roles
from consultation.models import Consultation, ExamenMedical, Hospitalisation, Rendez_vous, ResultatExamen
from consultation.views import _notifier_laborantin_examen
from facturation.models import Tarif
from facturation.regles import facturer
from patients.models import Patient
from personnel.models import Laborantin, Medecin


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        Tarif.objects.create(type_service='consultation', specialite='Généraliste',
                             nom='Consultation généraliste', prix=Decimal('5000'))
        Tarif.objects.create(type_service='hospitalisation', specialite='Urgence',
                             nom='Chambre urgence', prix=Decimal('20000'))
        self.patient = Patient.objects.create(
            nom='Keita', prenom='Moussa', sexe='Masculin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='70000000', email='k@example.com', numero_urgence='70000001')
        self.medecin = self.fiche_medecin('House')
        self.confrere = self.fiche_medecin('Wilson')
        self.compte_medecin = self.compte('dr_house', 'medecin', medecin=self.medecin)
        self.compte_confrere = self.compte('dr_wilson', 'medecin', medecin=self.confrere)
        self.accueil = self.compte('accueil', 'receptionniste')

    def fiche_medecin(self, nom):
        return Medecin.objects.create(nom=nom, prenom='G', telephone='1', service='Diag',
                                      specialite='Généraliste', role='medecin')

    def compte(self, nom, role, **liens):
        user = User.objects.create_user(nom, password='motdepasse-de-test')
        Profil.objects.create(user=user, role=Role.objects.get(code=role), **liens)
        return user

    def titres(self, user):
        return list(Notification.objects.filter(user=user).values_list('titre', flat=True))

    def rdv_du_jour(self, medecin=None):
        return Rendez_vous.objects.create(patient=self.patient, medecin=medecin or self.medecin,
                                          date=timezone.now(), statut='programme')


@override_settings(ALLOWED_HOSTS=['testserver'])
class PatientAdresseAuMedecinTests(Base):
    def prendre_rdv(self, medecin):
        self.client.force_login(self.accueil)
        return self.client.post(reverse('consultation:rdv_ajouter'), {
            'patient': self.patient.pk, 'medecin': medecin.pk,
            'date': '2026-12-01T09:00', 'statut': 'programme'})

    def test_seul_le_medecin_du_rendez_vous_est_prevenu(self):
        self.prendre_rdv(self.medecin)
        self.assertEqual(self.titres(self.compte_medecin), ['Nouveau rendez-vous'])
        self.assertEqual(self.titres(self.compte_confrere), [])
        self.assertEqual(self.titres(self.accueil), [])

    def test_la_notification_dit_quel_patient_et_quand(self):
        self.prendre_rdv(self.medecin)
        notification = Notification.objects.get(user=self.compte_medecin)
        self.assertIn('Keita', notification.message)
        self.assertIn('01/12/2026', notification.message)
        self.assertEqual(notification.url, reverse('consultation:rdv_liste'))

    def test_l_ecran_de_reception_previent_aussi_le_medecin(self):
        """C'est là que la réception enregistre un nouveau patient et le médecin qui le reçoit."""
        self.client.force_login(self.accueil)
        self.client.post(reverse('consultation:reception'), {
            'type_patient': 'nouveau', 'nom': 'Coulibaly', 'prenom': 'Awa', 'sexe': 'Féminin',
            'date_naissance': '1992-05-04', 'telephone': '70000000', 'adresse': 'Bamako',
            'numero_urgence': '70000001', 'medecin': self.medecin.pk,
            'date': '2026-12-01T09:00', 'mode_paiement': 'cash'})
        self.assertTrue(Rendez_vous.objects.filter(patient__nom='Coulibaly').exists())
        self.assertEqual(self.titres(self.compte_medecin), ['Nouveau rendez-vous'])

    def test_une_admission_d_urgence_previent_le_medecin_de_l_urgence(self):
        self.client.force_login(self.accueil)
        self.client.post(reverse('consultation:admission_urgence'), {
            'identite': 'inconnu', 'sexe': 'Masculin', 'age_approximatif': '40',
            'motif': 'accident_route', 'motif_precision': 'Collision moto',
            'medecin': self.medecin.pk, 'accompagnant_nom': 'Oumar Traoré',
            'accompagnant_lien': 'famille', 'accompagnant_telephone': '76000000'})
        notification = Notification.objects.get(user=self.compte_medecin)
        self.assertEqual(notification.titre, 'Patient en urgence')
        self.assertIn('à recevoir maintenant', notification.message)

    def _modifier(self, rdv, medecin):
        self.client.force_login(self.accueil)
        self.client.post(reverse('consultation:rdv_modifier', args=[rdv.pk]), {
            'patient': self.patient.pk, 'medecin': medecin.pk,
            'date': '2026-12-02T10:00', 'statut': 'programme'})

    def test_passer_le_rendez_vous_a_un_autre_medecin_previent_ce_medecin(self):
        rdv = self.rdv_du_jour()
        self._modifier(rdv, self.confrere)
        self.assertEqual(self.titres(self.compte_confrere), ['Nouveau rendez-vous'])
        self.assertEqual(self.titres(self.compte_medecin), [])

    def test_modifier_sans_changer_de_medecin_ne_previent_personne(self):
        rdv = self.rdv_du_jour()
        self._modifier(rdv, self.medecin)
        self.assertEqual(Notification.objects.count(), 0)

    def test_un_medecin_sans_compte_n_empeche_pas_le_rendez_vous(self):
        """Une fiche de médecin n'est pas forcément reliée à un compte."""
        sans_compte = self.fiche_medecin('Cameron')
        self.prendre_rdv(sans_compte)
        self.assertTrue(Rendez_vous.objects.filter(medecin=sans_compte).exists())
        self.assertEqual(Notification.objects.count(), 0)


@override_settings(ALLOWED_HOSTS=['testserver'])
class HospitalisationTests(Base):
    def hospitaliser(self, auteur):
        self.client.force_login(auteur)
        self.client.post(reverse('consultation:hospit_ajouter'), {
            'patient': self.patient.pk, 'medecin': self.medecin.pk, 'numero_chambre': '001',
            'etat_clinique': 'critique', 'nombre_jours': '2', 'date_entree': '2026-12-01'})
        self.assertEqual(Hospitalisation.objects.count(), 1)

    def test_enregistree_par_la_reception_le_medecin_est_prevenu(self):
        self.hospitaliser(self.accueil)
        notification = Notification.objects.get(user=self.compte_medecin)
        self.assertEqual(notification.titre, 'Patient hospitalisé')
        self.assertIn('chambre 001', notification.message)
        self.assertEqual(self.titres(self.accueil), [])
        self.assertEqual(self.titres(self.compte_confrere), [])

    def test_enregistree_par_le_medecin_la_reception_est_prevenue(self):
        """Sinon elle ne le sait pas, alors que c'est elle qui encaisse le séjour."""
        collegue = self.compte('accueil2', 'receptionniste')
        absente = self.compte('accueil3', 'receptionniste')
        User.objects.filter(pk=absente.pk).update(is_active=False)
        self.hospitaliser(self.compte_medecin)
        self.assertEqual(self.titres(self.accueil), ['Nouvelle hospitalisation'])
        self.assertEqual(self.titres(collegue), ['Nouvelle hospitalisation'])
        self.assertEqual(self.titres(absente), [])
        self.assertEqual(self.titres(self.compte_medecin), [])

    def test_le_lien_mene_au_sejour_et_la_page_s_ouvre_pour_la_reception(self):
        self.hospitaliser(self.compte_medecin)
        notification = Notification.objects.get(user=self.accueil)
        self.client.force_login(self.accueil)
        page = self.client.get(reverse('comptes:notification_ouvrir', args=[notification.pk]), follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.redirect_chain[-1][0], notification.url)
        notification.refresh_from_db()
        self.assertTrue(notification.lu)

    def test_enregistree_par_l_administrateur_les_deux_sont_prevenus(self):
        self.hospitaliser(self.compte('chef', 'admin'))
        self.assertEqual(self.titres(self.compte_medecin), ['Patient hospitalisé'])
        self.assertEqual(self.titres(self.accueil), ['Nouvelle hospitalisation'])


@override_settings(ALLOWED_HOSTS=['testserver'])
class ExamensTests(Base):
    def setUp(self):
        super().setUp()
        self.fiche_labo = Laborantin.objects.create(nom='Sidibe', prenom='A', telephone='2')
        self.labo = self.compte('labo', 'laborantin', laborantin=self.fiche_labo)
        consultation = Consultation.objects.create(rendez_vous=self.rdv_du_jour(), motif='Toux')
        self.examen = ExamenMedical.objects.create(
            patient=self.patient, consultation=consultation, laborantin=self.fiche_labo,
            medecin=self.medecin, type_examen='Prise de sang')

    def test_le_laborantin_recoit_la_demande_d_examen(self):
        _notifier_laborantin_examen(self.examen)
        self.assertEqual(self.titres(self.labo), ['Nouvel examen à réaliser'])
        self.assertEqual(self.titres(self.compte_medecin), [])

    def test_le_medecin_recoit_le_resultat_transmis_avec_une_icone_qui_existe(self):
        resultat = ResultatExamen.objects.create(
            patient=self.patient, examen=self.examen, medecin=self.medecin, resultat='Normal')
        self.client.force_login(self.labo)
        self.client.get(reverse('consultation:resultat_transmettre', args=[resultat.pk]))
        notification = Notification.objects.get(user=self.compte_medecin)
        self.assertEqual(notification.titre, "Résultat d'examen disponible")
        self.assertEqual(notification.icone, 'bi-clipboard2-pulse-fill')
        self.assertEqual(self.titres(self.compte_confrere), [])


@override_settings(ALLOWED_HOSTS=['testserver'])
class CompteursDeLaClocheTests(Base):
    """Un rendez-vous de chaque médecin, une facture impayée et un examen en attente."""

    def setUp(self):
        super().setUp()
        rdv = self.rdv_du_jour()
        self.rdv_du_jour(self.confrere)
        facturer(self.patient, 'rendez_vous', rdv)
        consultation = Consultation.objects.create(rendez_vous=rdv, motif='Toux')
        ExamenMedical.objects.create(patient=self.patient, consultation=consultation,
                                     medecin=self.medecin, type_examen='Radio', statut='en_attente')

    def cloche(self, user, adresse='dashboard'):
        self.client.force_login(user)
        return self.client.get(reverse(adresse)).context['cloche']

    def test_le_laborantin_ne_voit_ni_les_factures_ni_les_rendez_vous(self):
        self.client.force_login(self.compte('labo', 'laborantin'))
        page = self.client.get(reverse('dashboard'))
        self.assertEqual(page.context['cloche'], {'rdv': 0, 'factures': 0, 'examens': 0})
        self.assertNotContains(page, 'impayée')
        self.assertNotContains(page, "RDV aujourd'hui")

    def test_l_infirmier_ne_voit_rien_de_tout_cela(self):
        self.assertEqual(self.cloche(self.compte('inf', 'infirmier')),
                         {'rdv': 0, 'factures': 0, 'examens': 0})

    def test_le_medecin_ne_compte_que_ses_propres_rendez_vous(self):
        self.assertEqual(self.cloche(self.compte_medecin), {'rdv': 1, 'factures': 0, 'examens': 0})

    def test_un_medecin_sans_fiche_reliee_ne_compte_rien(self):
        self.assertEqual(self.cloche(self.compte('dr_seul', 'medecin'))['rdv'], 0)

    def test_la_reception_voit_tous_les_rendez_vous_et_ses_factures(self):
        self.client.force_login(self.accueil)
        page = self.client.get(reverse('dashboard'))
        self.assertEqual(page.context['cloche'], {'rdv': 2, 'factures': 1, 'examens': 0})
        self.assertContains(page, "2 RDV aujourd'hui")
        self.assertContains(page, '1 facture impayée')

    def test_le_pharmacien_ne_compte_que_les_factures_de_medicaments(self):
        """Celle-ci est une facture de consultation : elle ne le regarde pas."""
        self.assertEqual(self.cloche(self.compte('pharma', 'pharmacien')),
                         {'rdv': 0, 'factures': 0, 'examens': 0})

    def test_l_administrateur_voit_tout(self):
        self.assertEqual(self.cloche(self.compte('chef', 'admin')),
                         {'rdv': 2, 'factures': 1, 'examens': 1})

    def test_la_cloche_dit_la_meme_chose_sur_toutes_les_pages(self):
        """Avant, ces compteurs n'apparaissaient que sur le tableau de bord."""
        accueil = self.cloche(self.accueil)
        self.assertEqual(self.cloche(self.accueil, 'consultation:rdv_liste'), accueil)
