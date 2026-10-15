"""L'admission d'urgence : soigner d'abord, encaisser ensuite.

La règle de la clinique est « on paie avant d'être soigné ». Ces tests
vérifient les deux choses qui rendent son exception défendable :

  - elle DÉBLOQUE réellement le soin, sans quoi elle ne servirait à rien ;
  - elle N'EFFACE PAS la dette, sans quoi ce serait un trou dans la caisse.

Et le cas qui n'existait pas avant : admettre quelqu'un dont on ne sait
rien — ni le nom, ni l'adresse, ni l'adresse e-mail que le modèle exige.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import JournalAudit, Profil, Role
from comptes.roles import installer_roles
from consultation.models import Rendez_vous
from facturation.models import Derogation, Facture, Paiement, Tarif
from facturation.regles import blocage, facturer
from patients.models import Patient
from personnel.models import Medecin


@override_settings(ALLOWED_HOSTS=['testserver'])
class AdmissionUrgenceTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        Tarif.objects.create(type_service='consultation', specialite='Généraliste',
                             nom='Consultation généraliste', prix=Decimal('5000'))
        self.medecin = Medecin.objects.create(
            nom='House', prenom='G', telephone='1', service='Urgences',
            specialite='Généraliste', role='medecin')

        self.utilisateur = User.objects.create_user(
            'recept', password='motdepasse-de-test')
        Profil.objects.create(user=self.utilisateur,
                              role=Role.objects.get(code='receptionniste'))
        self.client.force_login(self.utilisateur)

    def admettre(self, **remplacements):
        donnees = {
            'identite': 'inconnu',
            'sexe': 'Masculin',
            'age_approximatif': '40',
            'motif': 'accident_route',
            'motif_precision': 'Collision moto, patient inconscient',
            'medecin': self.medecin.pk,
            'accompagnant_nom': 'Oumar Traoré',
            'accompagnant_lien': 'famille',
            'accompagnant_telephone': '76000000',
        }
        donnees.update(remplacements)
        return self.client.post(reverse('consultation:admission_urgence'), donnees)

    # --- admettre quelqu'un dont on ne sait rien ---

    def test_un_inconnu_peut_etre_admis(self):
        """Avant : les 8 champs obligatoires rendaient la chose impossible."""
        self.admettre()

        patient = Patient.objects.get()
        self.assertTrue(patient.identite_provisoire)
        self.assertEqual(patient.nom, 'INCONNU')
        self.assertEqual(patient.sexe, 'Masculin')
        # L'age approximatif devient un reperage, pas une fausse precision.
        self.assertEqual(patient.date_naissance.year, date.today().year - 40)

    def test_les_inconnus_sont_numerotes(self):
        self.admettre()
        self.admettre()

        noms = sorted(p.prenom for p in Patient.objects.all())
        self.assertEqual(noms, ['n°1', 'n°2'])

    def test_un_patient_nomme_garde_son_nom(self):
        self.admettre(identite='nomme', nom='Keita', prenom='Moussa')

        patient = Patient.objects.get()
        self.assertEqual(patient.nom, 'Keita')
        self.assertTrue(patient.identite_provisoire)

    def test_un_patient_connu_nest_pas_recree(self):
        existant = Patient.objects.create(
            nom='Diallo', prenom='Fanta', sexe='Féminin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='70000000', email='f@example.com', numero_urgence='70000001')

        self.admettre(identite='existant', patient=existant.pk)

        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(Derogation.objects.get().facture.patient, existant)

    # --- le soin est reellement debloque ---

    def test_le_soin_nest_plus_bloque(self):
        self.admettre()
        rdv = Rendez_vous.objects.get()

        # Sans derogation, blocage() refuserait : la facture n'est pas reglee.
        self.assertIsNone(blocage('rendez_vous', rdv))

    def test_sans_derogation_le_soin_reste_bloque(self):
        """Le temoin : la regle normale n'a pas ete affaiblie pour autant."""
        patient = Patient.objects.create(
            nom='Bah', prenom='Mama', sexe='Féminin',
            date_naissance=date(1990, 1, 1), adresse='Bamako',
            telephone='70000000', email='b@example.com', numero_urgence='70000001')
        rdv = Rendez_vous.objects.create(
            patient=patient, medecin=self.medecin, date='2026-12-01T09:00')
        facturer(patient, 'rendez_vous', rdv)

        self.assertIsNotNone(blocage('rendez_vous', rdv))

    # --- la dette n'est pas effacee ---

    def test_la_facture_reste_due(self):
        self.admettre()

        facture = Facture.objects.get()
        self.assertFalse(facture.est_reglee())
        self.assertEqual(facture.montant_restant(), Decimal('5000'))
        self.assertEqual(Paiement.objects.count(), 0)

    def test_la_derogation_garde_qui_et_pourquoi(self):
        self.admettre()

        derogation = Derogation.objects.get()
        self.assertEqual(derogation.accordee_par, self.utilisateur)
        self.assertEqual(derogation.motif, 'accident_route')
        self.assertIn('inconscient', derogation.motif_precision)
        self.assertEqual(derogation.accompagnant_nom, 'Oumar Traoré')
        self.assertEqual(derogation.accompagnant_lien, 'famille')
        self.assertEqual(derogation.accompagnant_telephone, '76000000')

    def test_sans_motif_pas_dadmission(self):
        """La seule barriere, et elle ne coute aucune seconde."""
        reponse = self.admettre(motif='')

        self.assertEqual(Derogation.objects.count(), 0)
        self.assertEqual(Patient.objects.count(), 0)
        self.assertContains(reponse, 'obligatoire')

    def test_autre_sans_precision_est_refuse(self):
        """« Autre » sans explication ne justifie rien."""
        reponse = self.admettre(motif='autre', motif_precision='')

        self.assertEqual(Derogation.objects.count(), 0)
        self.assertContains(reponse, 'précisez')

    def test_autre_avec_precision_passe(self):
        self.admettre(motif='autre', motif_precision='Morsure de serpent')

        derogation = Derogation.objects.get()
        self.assertEqual(derogation.motif, 'autre')
        # Pour « autre », la précision EST le motif : pas de doublon à l'écran.
        self.assertEqual(derogation.motif_complet(), 'Morsure de serpent')

    def test_un_motif_de_la_liste_se_lit_en_clair(self):
        self.admettre()

        derogation = Derogation.objects.get()
        self.assertEqual(
            derogation.motif_complet(),
            'Accident de la route — Collision moto, patient inconscient')

    def test_un_motif_de_la_liste_se_passe_de_precision(self):
        self.admettre(motif='hemorragie', motif_precision='')

        self.assertEqual(Derogation.objects.get().motif_complet(), 'Hémorragie')

    def test_le_lien_de_laccompagnant_est_conserve(self):
        """Le cas qu'elle a décrit : l'autre partie de l'accident."""
        self.admettre(accompagnant_nom='Sekou Bah',
                      accompagnant_lien='implique_accident')

        derogation = Derogation.objects.get()
        self.assertEqual(
            derogation.accompagnant_complet(),
            "Sekou Bah (impliqué dans l'accident)")

    def test_un_accompagnant_sans_lien_reste_lisible(self):
        self.admettre(accompagnant_nom='Oumar Traoré', accompagnant_lien='')

        self.assertEqual(
            Derogation.objects.get().accompagnant_complet(), 'Oumar Traoré')

    def test_un_patient_arrive_seul(self):
        self.admettre(accompagnant_nom='', accompagnant_lien='aucun',
                      accompagnant_telephone='')

        self.assertEqual(
            Derogation.objects.get().accompagnant_complet(),
            'Personne — patient arrivé seul')

    def test_laudit_garde_la_trace(self):
        self.admettre()

        trace = JournalAudit.objects.filter(modele='Derogation').first()
        self.assertIsNotNone(trace)
        self.assertEqual(trace.user, self.utilisateur)
        self.assertIn('urgence', trace.details.lower())

    # --- le suivi ---

    def test_lecran_de_suivi_montre_ce_qui_reste_du(self):
        self.admettre()

        reponse = self.client.get(reverse('consultation:soins_sans_paiement'))

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(reponse.context['en_cours']), 1)
        self.assertEqual(reponse.context['total_differe'], Decimal('5000'))
        self.assertEqual(reponse.context['a_identifier'], 1)
        # Le numero de l'accompagnant doit sauter aux yeux : c'est lui qu'on rappelle.
        self.assertContains(reponse, '76000000')

    def test_une_fois_payee_la_derogation_sort_de_la_liste(self):
        self.admettre()
        facture = Facture.objects.get()
        Paiement.objects.create(facture=facture, montant=Decimal('5000'),
                                mode_paiement='cash')

        reponse = self.client.get(reverse('consultation:soins_sans_paiement'))

        self.assertEqual(reponse.context['en_cours'], [])
        self.assertEqual(len(reponse.context['reglees']), 1)
        self.assertFalse(Derogation.objects.get().est_active())

    def test_tout_echoue_ensemble_ou_rien(self):
        """Un medecin inexistant ne doit pas laisser un patient orphelin."""
        self.admettre(medecin=99999)

        self.assertEqual(Patient.objects.count(), 0)
        self.assertEqual(Rendez_vous.objects.count(), 0)
        self.assertEqual(Derogation.objects.count(), 0)
