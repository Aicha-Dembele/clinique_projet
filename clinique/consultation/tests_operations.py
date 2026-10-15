"""Le bloc opératoire : programmer, facturer, puis opérer une fois réglé.

Une opération suit le protocole de la clinique comme les autres actes : elle
est facturée dès sa programmation, et ne peut être RÉALISÉE qu'une fois la
facture encaissée. Avec l'exception qui compte : une césarienne admise en
urgence n'attend pas que la famille trouve 150 000 FCFA.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Operation
from facturation.models import Derogation, Facture, Paiement, Tarif
from facturation.regles import blocage, facture_de
from patients.models import Patient
from personnel.models import Medecin


@override_settings(ALLOWED_HOSTS=['testserver'])
class OperationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        Tarif.objects.create(type_service='operation', specialite='Césarienne',
                             nom='Césarienne', prix=Decimal('150000'))
        Tarif.objects.create(type_service='operation', specialite='Hernie',
                             nom='Cure de hernie', prix=Decimal('110000'))

        self.chirurgien = Medecin.objects.create(
            nom='Touré', prenom='Awa', telephone='1', service='Chirurgie',
            specialite='Chirurgie', role='medecin')
        self.patiente = Patient.objects.create(
            nom='Diallo', prenom='Fanta', sexe='Féminin',
            date_naissance=date(1995, 1, 1), adresse='Bamako',
            telephone='70000000', email='f@example.com', numero_urgence='70000001')

        self.medecin_user = User.objects.create_user(
            'chir', password='motdepasse-de-test')
        Profil.objects.create(user=self.medecin_user,
                              role=Role.objects.get(code='medecin'),
                              medecin=self.chirurgien)
        self.client.force_login(self.medecin_user)

    def programmer(self, **remplacements):
        donnees = {
            'patient': self.patiente.pk,
            'chirurgien': self.chirurgien.pk,
            'type_operation': 'Césarienne',
            'motif': 'Présentation par le siège',
            'date': '2026-11-02',
        }
        donnees.update(remplacements)
        return self.client.post(
            reverse('consultation:operation_ajouter'), donnees)

    # --- la facturation ---

    def test_programmer_etablit_la_facture_au_bon_tarif(self):
        self.programmer()

        operation = Operation.objects.get()
        facture = facture_de('operation', operation)
        self.assertIsNotNone(facture)
        self.assertEqual(facture.montant_total, Decimal('150000'))

    def test_le_tarif_suit_le_type_dintervention(self):
        self.programmer(type_operation='Hernie')

        facture = facture_de('operation', Operation.objects.get())
        self.assertEqual(facture.montant_total, Decimal('110000'))

    def test_chaque_operation_a_sa_propre_facture(self):
        """L'assurance s'applique prestation par prestation, pas en bloc."""
        self.programmer()
        self.programmer(type_operation='Hernie')

        self.assertEqual(Facture.objects.count(), 2)
        self.assertEqual(
            sorted(f.montant_total for f in Facture.objects.all()),
            [Decimal('110000'), Decimal('150000')])

    def test_sans_type_dintervention_rien_nest_cree(self):
        self.programmer(type_operation='')

        self.assertEqual(Operation.objects.count(), 0)

    # --- le blocage ---

    def test_le_bloc_est_ferme_tant_que_ce_nest_pas_regle(self):
        self.programmer()
        operation = Operation.objects.get()

        self.assertIsNotNone(blocage('operation', operation))

    def test_le_compte_rendu_est_refuse_avant_paiement(self):
        self.programmer()
        operation = Operation.objects.get()

        self.client.post(
            reverse('consultation:operation_realiser', args=[operation.pk]),
            {'compte_rendu': 'Intervention réalisée', 'statut': 'terminee'})

        operation.refresh_from_db()
        self.assertEqual(operation.compte_rendu, '')
        self.assertEqual(operation.statut, 'programmee')

    def test_une_fois_payee_le_compte_rendu_passe(self):
        self.programmer()
        operation = Operation.objects.get()
        facture = facture_de('operation', operation)
        Paiement.objects.create(facture=facture, montant=Decimal('150000'),
                                mode_paiement='cash')

        self.client.post(
            reverse('consultation:operation_realiser', args=[operation.pk]),
            {'compte_rendu': 'Césarienne réalisée sans complication',
             'statut': 'terminee'})

        operation.refresh_from_db()
        self.assertIn('sans complication', operation.compte_rendu)
        self.assertEqual(operation.statut, 'terminee')

    def test_une_urgence_ouvre_le_bloc_sans_effacer_la_dette(self):
        """Le point qui compte : une césarienne vitale n'attend pas."""
        self.programmer()
        operation = Operation.objects.get()
        facture = facture_de('operation', operation)
        Derogation.objects.create(
            facture=facture, accordee_par=self.medecin_user,
            motif='Souffrance fœtale aiguë')

        self.assertIsNone(blocage('operation', operation))
        # La dette court toujours.
        self.assertFalse(facture.est_reglee())
        self.assertEqual(facture.montant_restant(), Decimal('150000'))

    # --- le cloisonnement ---

    def test_le_dossier_est_rattache_au_chirurgien(self):
        self.programmer()

        operation = Operation.objects.get()
        self.assertIsNotNone(operation.dossier)
        self.assertEqual(operation.dossier.medecin, self.chirurgien)

    def test_un_chirurgien_ne_voit_que_ses_interventions(self):
        autre = Medecin.objects.create(
            nom='Keita', prenom='B', telephone='2', service='Chirurgie',
            specialite='Chirurgie', role='medecin')
        Operation.objects.create(patient=self.patiente, chirurgien=autre,
                                 type_operation='Hernie')
        self.programmer()

        reponse = self.client.get(reverse('consultation:operations'))

        listees = [item['operation'] for item in reponse.context['operations']]
        self.assertEqual(len(listees), 1)
        self.assertEqual(listees[0].chirurgien, self.chirurgien)

    def test_lintervention_dun_confrere_donne_404(self):
        autre = Medecin.objects.create(
            nom='Keita', prenom='B', telephone='2', service='Chirurgie',
            specialite='Chirurgie', role='medecin')
        sienne = Operation.objects.create(
            patient=self.patiente, chirurgien=autre, type_operation='Hernie')

        reponse = self.client.get(
            reverse('consultation:operation_realiser', args=[sienne.pk]))

        self.assertEqual(reponse.status_code, 404)

    # --- les permissions ---

    def test_la_reception_voit_mais_ne_programme_pas(self):
        self.programmer()
        recept = User.objects.create_user('recept', password='motdepasse-de-test')
        Profil.objects.create(user=recept,
                              role=Role.objects.get(code='receptionniste'))
        self.client.force_login(recept)

        self.assertEqual(
            self.client.get(reverse('consultation:operations')).status_code, 200)
        # Programmer est refuse : elle n'a pas operation.add.
        self.assertEqual(
            self.client.get(
                reverse('consultation:operation_ajouter')).status_code, 302)
