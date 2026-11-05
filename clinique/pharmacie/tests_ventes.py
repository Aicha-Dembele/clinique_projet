"""Ventes, profits et factures fournisseurs de la pharmacie."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from comptes.models import Profil, Role
from comptes.roles import installer_roles
from consultation.models import Consultation, Ordonnance, Rendez_vous
from facturation.models import Facture
from patients.models import Patient
from personnel.models import Medecin
from pharmacie import ventes as calculs
from pharmacie.models import Commande, Fournisseur, LigneCommande, Lot, Medicament, MouvementStock


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        installer_roles()

    def setUp(self):
        # Les migrations installent le catalogue réel et ses lots de départ : on repart de zéro.
        Lot.objects.all().delete()
        self.medicament = Medicament.objects.create(
            nom='Testamol', unite='boîte', prix_unitaire=Decimal('500'))
        medecin = Medecin.objects.create(nom='House', prenom='G', telephone='1', service='Diag',
                                         specialite='Généraliste', role='medecin')
        self.patient = Patient.objects.create(
            nom='Keita', prenom='Moussa', sexe='Masculin', date_naissance=date(1990, 1, 1),
            adresse='Bamako', telephone='70000000', email='k@example.com', numero_urgence='70000001')
        rdv = Rendez_vous.objects.create(patient=self.patient, medecin=medecin, date=timezone.now())
        consultation = Consultation.objects.create(rendez_vous=rdv, motif='Fièvre')
        self.ordonnance = Ordonnance.objects.create(consultation=consultation, date=date(2026, 11, 1),
                                                    medicaments='Testamol')
        self.facture = Facture.objects.create(patient=self.patient, ordonnance=self.ordonnance)

    def arrivage(self, quantite, prix_achat=None, medicament=None, peremption=None, **autres):
        mouvement = MouvementStock(medicament=medicament or self.medicament, type_mouvement='entree',
                                   quantite=quantite)
        mouvement.lot_prix_achat = prix_achat
        mouvement.lot_peremption = peremption
        for cle, valeur in autres.items():
            setattr(mouvement, f'lot_{cle}', valeur)
        mouvement.save()
        return Lot.objects.order_by('-pk').first()

    def vendre(self, quantite, prix=None, medicament=None, quand=None):
        mouvement = MouvementStock.objects.create(
            medicament=medicament or self.medicament, type_mouvement='sortie', quantite=quantite,
            prix_unitaire=prix or Decimal('500'), facture=self.facture,
            patient=self.patient, ordonnance=self.ordonnance)
        if quand:
            MouvementStock.objects.filter(pk=mouvement.pk).update(date=quand)
        return mouvement

    def connecter(self, role):
        user = User.objects.create_user(f'compte_{role}', password='motdepasse-de-test')
        Profil.objects.create(user=user, role=Role.objects.get(code=role))
        self.client.force_login(user)
        return user


class StockDeDepartTests(TestCase):
    def test_il_attend_son_prix_d_achat(self):
        """Il avait reçu le prix de vente à la place : le profit aurait été nul et faux."""
        lots = Lot.objects.filter(numero=Lot.NUMERO_INITIAL)
        self.assertTrue(lots.exists())
        self.assertFalse(lots.exclude(prix_achat=0).exists())


class CalculDuProfitTests(Base):
    def test_le_profit_est_le_prix_de_vente_moins_le_vrai_prix_d_achat(self):
        self.arrivage(100, prix_achat=Decimal('300'))
        self.vendre(10)
        total = calculs.resume()['jour']
        self.assertEqual(total.vendu, Decimal('5000'))
        self.assertEqual(total.cout, Decimal('3000'))
        self.assertEqual(total.profit, Decimal('2000'))
        self.assertEqual(total.marge, 40)

    def test_une_vente_sur_deux_arrivages_prend_le_prix_de_chacun(self):
        """Le premier lot à périmer sort d'abord : 4 boîtes à 300, puis 6 à 400."""
        aujourdhui = timezone.localdate()
        self.arrivage(4, Decimal('300'), peremption=aujourdhui + timedelta(days=30))
        self.arrivage(50, Decimal('400'), peremption=aujourdhui + timedelta(days=300))
        self.vendre(10)
        total = calculs.resume()['jour']
        self.assertEqual(total.cout, Decimal('3600'))
        self.assertEqual(total.profit, Decimal('1400'))

    def test_le_prix_de_vente_est_celui_du_jour_de_la_vente(self):
        self.arrivage(100, Decimal('300'))
        self.vendre(10)
        Medicament.objects.filter(pk=self.medicament.pk).update(prix_unitaire=Decimal('900'))
        self.assertEqual(calculs.resume()['jour'].vendu, Decimal('5000'))

    def test_une_sortie_interne_n_est_pas_une_vente(self):
        self.arrivage(100, Decimal('300'))
        MouvementStock.objects.create(medicament=self.medicament, type_mouvement='sortie',
                                      quantite=5, motif='Périmé')
        self.assertEqual(calculs.ventes(), [])

    def test_sans_prix_d_achat_la_vente_compte_mais_pas_le_profit(self):
        """Un coût de zéro donnerait un profit inventé : c'est signalé à la place."""
        self.arrivage(100)
        self.vendre(10)
        total = calculs.resume()['jour']
        self.assertEqual(total.vendu, Decimal('5000'))
        self.assertEqual(total.quantite_sans_prix, 10)
        self.assertEqual(total.profit, Decimal('0'))
        self.assertFalse(total.cout_connu)
        self.assertIsNone(total.marge)

    def test_un_lot_sans_prix_et_un_lot_avec_prix_sont_comptes_separement(self):
        aujourdhui = timezone.localdate()
        self.arrivage(4, peremption=aujourdhui + timedelta(days=30))
        self.arrivage(50, Decimal('400'), peremption=aujourdhui + timedelta(days=300))
        self.vendre(10)
        total = calculs.resume()['jour']
        self.assertEqual(total.quantite_sans_prix, 4)
        self.assertEqual(total.cout, Decimal('2400'))
        self.assertEqual(total.profit, Decimal('600'))
        self.assertTrue(total.cout_connu)

    def test_saisir_le_prix_du_lot_corrige_les_ventes_deja_faites(self):
        lot = self.arrivage(100)
        self.vendre(10)
        Lot.objects.filter(pk=lot.pk).update(prix_achat=Decimal('300'))
        self.assertEqual(calculs.resume()['jour'].profit, Decimal('2000'))

    def test_une_entree_sans_prix_d_achat_ne_recopie_plus_le_prix_de_vente(self):
        lot = self.arrivage(100)
        self.assertEqual(lot.prix_achat, Decimal('0'))


class PeriodesTests(Base):
    def setUp(self):
        super().setUp()
        self.arrivage(1000, Decimal('300'))
        # Un mercredi : le lundi de sa semaine est dans le même mois.
        self.jour = date(2026, 11, 18)

    def quand(self, jour):
        return timezone.make_aware(timezone.datetime(jour.year, jour.month, jour.day, 12, 0))

    def test_jour_semaine_et_mois_ne_comptent_que_leur_periode(self):
        self.vendre(1, quand=self.quand(self.jour))
        self.vendre(2, quand=self.quand(date(2026, 11, 16)))   # lundi de la semaine
        self.vendre(4, quand=self.quand(date(2026, 11, 15)))   # dimanche d'avant, même mois
        self.vendre(8, quand=self.quand(date(2026, 10, 31)))   # autre mois
        resume = calculs.resume(calculs.ventes(), self.jour)
        self.assertEqual(resume['jour'].quantite, 1)
        self.assertEqual(resume['semaine'].quantite, 3)
        self.assertEqual(resume['mois'].quantite, 7)

    def test_le_detail_par_jour_et_par_semaine_suit_les_ventes(self):
        self.vendre(1, quand=self.quand(self.jour))
        self.vendre(2, quand=self.quand(date(2026, 11, 16)))
        self.vendre(4, quand=self.quand(date(2026, 11, 10)))
        lignes = calculs.ventes()
        self.assertEqual([(p.libelle, p.quantite) for p in calculs.par_jour(lignes, aujourdhui=self.jour)],
                         [('18/11/2026', 1), ('16/11/2026', 2), ('10/11/2026', 4)])
        self.assertEqual([(p.libelle, p.quantite) for p in calculs.par_semaine(lignes, aujourdhui=self.jour)],
                         [('Semaine du 16/11/2026', 3), ('Semaine du 09/11/2026', 4)])

    def test_le_detail_par_mois_montre_aussi_les_mois_sans_vente(self):
        self.vendre(1, quand=self.quand(self.jour))
        self.vendre(2, quand=self.quand(date(2026, 9, 5)))
        mois = calculs.par_mois(calculs.ventes(), aujourdhui=self.jour)
        self.assertEqual(len(mois), 12)
        self.assertEqual([(m.libelle, m.quantite) for m in mois[:3]],
                         [('Novembre 2026', 1), ('Octobre 2026', 0), ('Septembre 2026', 2)])

    def test_le_changement_d_annee_ne_perd_pas_de_mois(self):
        mois = calculs.par_mois([], nombre=3, aujourdhui=date(2027, 1, 10))
        self.assertEqual([m.libelle for m in mois], ['Janvier 2027', 'Décembre 2026', 'Novembre 2026'])

    def test_le_profit_par_medicament_est_range_du_plus_rentable_au_moins_rentable(self):
        autre = Medicament.objects.create(nom='Autrement', unite='boîte', prix_unitaire=Decimal('1000'))
        self.arrivage(100, Decimal('200'), medicament=autre)
        self.vendre(5, quand=self.quand(self.jour))                                     # 5 × 200 = 1 000
        self.vendre(5, prix=Decimal('1000'), medicament=autre, quand=self.quand(self.jour))  # 5 × 800 = 4 000
        self.vendre(5, quand=self.quand(date(2026, 10, 5)))                             # autre mois
        totaux = calculs.par_medicament(calculs.ventes(), 2026, 11)
        self.assertEqual([(t.medicament.nom, t.quantite, t.profit) for t in totaux],
                         [('Autrement', 5, Decimal('4000')), ('Testamol', 5, Decimal('1000'))])


class FacturesFournisseursTests(Base):
    def setUp(self):
        super().setUp()
        self.fournisseur = Fournisseur.objects.create(nom='Grossiste Test')

    def commande(self, statut=Commande.Statut.ENVOYEE):
        commande = Commande.objects.create(fournisseur=self.fournisseur, statut=statut)
        ligne = LigneCommande.objects.create(commande=commande, medicament=self.medicament,
                                             quantite=100, prix_achat=Decimal('300'))
        return commande, ligne

    def test_une_commande_non_recue_n_est_pas_une_facture(self):
        self.commande()
        self.assertEqual(calculs.factures_fournisseurs(), [])

    def test_une_livraison_partielle_ne_compte_que_ce_qui_est_arrive(self):
        _, ligne = self.commande()
        ligne.receptionner(40)
        facture = calculs.factures_fournisseurs()[0]
        self.assertEqual(facture.montant, Decimal('12000'))
        self.assertEqual(facture.statut, 'Livraison partielle')
        self.assertIn('Testamol × 40', facture.detail)

    def test_le_lot_recu_garde_sa_commande_et_n_apparait_pas_deux_fois(self):
        commande, ligne = self.commande()
        ligne.receptionner(40)
        self.assertEqual(Lot.objects.get().commande, commande)
        self.assertEqual(len(calculs.factures_fournisseurs()), 1)

    def test_une_entree_sans_commande_est_un_achat_a_part_entiere(self):
        self.arrivage(10, Decimal('300'), fournisseur=self.fournisseur)
        facture = calculs.factures_fournisseurs()[0]
        self.assertEqual(facture.montant, Decimal('3000'))
        self.assertEqual(facture.fournisseur, 'Grossiste Test')
        self.assertEqual(facture.statut, 'Entrée sans commande')

    def test_le_stock_de_depart_n_est_pas_un_achat(self):
        Lot.objects.create(medicament=self.medicament, numero=Lot.NUMERO_INITIAL,
                           quantite_initiale=10, quantite_restante=10)
        self.assertEqual(calculs.factures_fournisseurs(), [])

    def test_un_achat_sans_prix_est_signale(self):
        self.arrivage(10)
        self.assertTrue(calculs.factures_fournisseurs()[0].prix_manquant)


@override_settings(ALLOWED_HOSTS=['testserver'])
class PagesTests(Base):
    def test_le_pharmacien_voit_ses_deux_facturations_et_ses_ventes_dans_le_menu(self):
        self.connecter('pharmacien')
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, 'Factures clients')
        self.assertContains(page, reverse('pharmacie:factures_fournisseurs'))
        self.assertContains(page, reverse('pharmacie:ventes'))
        self.assertContains(page, 'Vendu cette semaine')

    def test_le_tableau_de_bord_du_pharmacien_montre_les_vraies_ventes(self):
        self.arrivage(100, Decimal('300'))
        self.vendre(10)
        self.connecter('pharmacien')
        contexte = self.client.get(reverse('dashboard')).context
        self.assertEqual(contexte['ventes']['jour'].vendu, Decimal('5000'))
        self.assertEqual(contexte['ventes']['mois'].profit, Decimal('2000'))

    def test_la_page_des_ventes_affiche_les_chiffres_du_mois(self):
        self.arrivage(100, Decimal('300'))
        self.vendre(10)
        self.connecter('pharmacien')
        page = self.client.get(reverse('pharmacie:ventes'))
        self.assertContains(page, '5 000 FCFA')
        self.assertContains(page, '2 000 FCFA')
        self.assertContains(page, 'Testamol')
        self.assertNotContains(page, "pas de prix d'achat")

    def test_les_trois_vues_et_un_mois_mal_ecrit_ne_cassent_rien(self):
        self.connecter('pharmacien')
        for adresse in ('?vue=semaine', '?vue=mois', '?vue=nimporte', '?mois=abc', '?mois=2026-13', '?mois='):
            self.assertEqual(self.client.get(reverse('pharmacie:ventes') + adresse).status_code, 200, adresse)

    def test_la_page_previent_quand_des_prix_d_achat_manquent(self):
        self.arrivage(100)
        self.vendre(10)
        self.connecter('pharmacien')
        page = self.client.get(reverse('pharmacie:ventes'))
        self.assertContains(page, "Saisir les prix d")
        self.assertContains(page, "1 lot n'a pas de prix d'achat")
        self.assertEqual(page.context['nb_lots_sans_prix'], 1)

    def test_la_page_des_factures_fournisseurs_s_affiche_et_se_filtre(self):
        fournisseur = Fournisseur.objects.create(nom='Grossiste Test')
        self.arrivage(10, Decimal('300'), fournisseur=fournisseur)
        self.connecter('pharmacien')
        adresse = reverse('pharmacie:factures_fournisseurs')
        page = self.client.get(adresse)
        self.assertContains(page, 'Grossiste Test')
        self.assertContains(page, '3 000 FCFA')
        autre = Fournisseur.objects.create(nom='Autre Grossiste')
        self.assertEqual(self.client.get(adresse, {'fournisseur': autre.pk}).context['factures'], [])
        self.assertEqual(len(self.client.get(adresse, {'fournisseur': fournisseur.pk}).context['factures']), 1)
        self.assertEqual(self.client.get(adresse, {'mois': '2001-01'}).context['factures'], [])

    def test_ces_pages_sont_reservees_a_la_pharmacie(self):
        """Le profit et les prix d'achat ne regardent ni l'accueil, ni les soignants."""
        for role in ('receptionniste', 'medecin', 'infirmier', 'laborantin'):
            self.connecter(role)
            for nom in ('pharmacie:ventes', 'pharmacie:factures_fournisseurs'):
                self.assertEqual(self.client.get(reverse(nom)).status_code, 302, (role, nom))
            self.client.logout()

    def test_les_factures_clients_ne_changent_pas_de_nom_a_l_accueil(self):
        self.connecter('receptionniste')
        page = self.client.get(reverse('dashboard'))
        self.assertNotContains(page, 'Factures clients')
        self.assertNotContains(page, reverse('pharmacie:ventes'))


@override_settings(ALLOWED_HOSTS=['testserver'])
class SaisieDesPrixDAchatTests(Base):
    def setUp(self):
        super().setUp()
        self.lot = self.arrivage(100)
        self.adresse = reverse('pharmacie:lots_prix_achat')

    def test_tous_les_lots_sans_prix_sont_sur_une_seule_page(self):
        autre = self.arrivage(10)
        self.arrivage(10, Decimal('300'))
        self.connecter('pharmacien')
        page = self.client.get(self.adresse)
        self.assertEqual({l.pk for l in page.context['lots']}, {self.lot.pk, autre.pk})
        self.assertContains(page, f'name="prix_{self.lot.pk}"')

    def test_le_pharmacien_saisit_les_prix_et_le_profit_apparait(self):
        autre = self.arrivage(10)
        self.vendre(10)
        self.connecter('pharmacien')
        self.client.post(self.adresse, {f'prix_{self.lot.pk}': '300', f'prix_{autre.pk}': '350'})
        self.lot.refresh_from_db()
        autre.refresh_from_db()
        self.assertEqual(self.lot.prix_achat, Decimal('300'))
        self.assertEqual(autre.prix_achat, Decimal('350'))
        self.assertTrue(calculs.resume()['jour'].cout_connu)
        self.assertGreater(calculs.resume()['jour'].profit, 0)

    def test_une_case_vide_ne_change_rien(self):
        autre = self.arrivage(10)
        self.connecter('pharmacien')
        self.client.post(self.adresse, {f'prix_{self.lot.pk}': '300', f'prix_{autre.pk}': ''})
        autre.refresh_from_db()
        self.assertEqual(autre.prix_achat, Decimal('0'))
        self.assertEqual({l.pk for l in self.client.get(self.adresse).context['lots']}, {autre.pk})

    def test_un_prix_invalide_est_refuse_sans_bloquer_les_autres(self):
        autre = self.arrivage(10)
        self.connecter('pharmacien')
        for mauvais in ('-5', 'abc', 'NaN', 'Infinity'):
            self.client.post(self.adresse, {f'prix_{self.lot.pk}': mauvais, f'prix_{autre.pk}': ''})
            self.lot.refresh_from_db()
            self.assertEqual(self.lot.prix_achat, Decimal('0'), mauvais)
        page = self.client.post(self.adresse, {f'prix_{self.lot.pk}': 'abc', f'prix_{autre.pk}': '350'}, follow=True)
        self.assertContains(page, 'Prix non valide')
        autre.refresh_from_db()
        self.assertEqual(autre.prix_achat, Decimal('350'))

    def test_on_peut_corriger_un_prix_deja_saisi(self):
        self.arrivage(10, Decimal('300'), medicament=self.medicament)
        lot = Lot.objects.order_by('-pk').first()
        self.connecter('pharmacien')
        adresse = f'{self.adresse}?medicament={self.medicament.pk}'
        self.assertContains(self.client.get(adresse), 'value="300"')
        self.assertRedirects(self.client.post(adresse, {f'prix_{lot.pk}': '320'}), adresse,
                             fetch_redirect_response=False)
        lot.refresh_from_db()
        self.assertEqual(lot.prix_achat, Decimal('320'))

    def test_seule_la_pharmacie_peut_les_modifier(self):
        self.connecter('receptionniste')
        self.assertEqual(self.client.post(self.adresse, {f'prix_{self.lot.pk}': '300'}).status_code, 302)
        self.lot.refresh_from_db()
        self.assertEqual(self.lot.prix_achat, Decimal('0'))

    def test_quand_il_ne_manque_plus_rien_la_page_le_dit(self):
        Lot.objects.filter(pk=self.lot.pk).update(prix_achat=Decimal('300'))
        self.connecter('pharmacien')
        self.assertContains(self.client.get(self.adresse), "Tous les lots ont leur prix d")
