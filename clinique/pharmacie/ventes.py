"""Ce que la pharmacie vend, ce qu'elle achète, et ce qu'elle y gagne.

Une VENTE est une sortie de stock portée sur une facture : un médicament dispensé à
un client avec son ordonnance. Les sorties internes (péremption, soin infirmier,
ajustement) n'ont pas de facture : ce ne sont pas des ventes.

Le PROFIT se calcule boîte par boîte : le prix de vente figé sur le mouvement, moins
le prix d'achat du lot dont la boîte est vraiment sortie (SortieLot). Deux arrivages
achetés à des prix différents donnent donc deux marges différentes.

Une boîte dont le lot n'a pas de prix d'achat compte dans le vendu, mais pas dans le
profit : l'afficher avec un coût de zéro donnerait un profit inventé. Elle est comptée
à part (`quantite_sans_prix`) pour que l'écran puisse le dire.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from .models import Commande, Lot, MouvementStock

MOIS_FR = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet',
           'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']


@dataclass
class Cumul:
    """Un total : une vente seule, une journée, un mois ou un médicament."""
    libelle: str = ''
    quantite: int = 0
    vendu: Decimal = Decimal('0')
    cout: Decimal = Decimal('0')
    quantite_sans_prix: int = 0
    vendu_sans_prix: Decimal = Decimal('0')

    def ajouter(self, autre):
        self.quantite += autre.quantite
        self.vendu += autre.vendu
        self.cout += autre.cout
        self.quantite_sans_prix += autre.quantite_sans_prix
        self.vendu_sans_prix += autre.vendu_sans_prix

    @property
    def profit(self):
        return self.vendu - self.vendu_sans_prix - self.cout

    @property
    def marge(self):
        """Profit en % du vendu, sur les seules boîtes dont le coût est connu."""
        base = self.vendu - self.vendu_sans_prix
        return round(self.profit * 100 / base) if base else None

    @property
    def cout_connu(self):
        """Faux si aucune boîte de ce total n'a de prix d'achat : il n'y a pas de profit à afficher."""
        return self.quantite > self.quantite_sans_prix


@dataclass
class Vente(Cumul):
    jour: date = None
    medicament: object = None


def debut_de_journee(jour):
    return timezone.make_aware(datetime.combine(jour, time.min))


def ventes(depuis=None):
    """Toutes les ventes, de la plus ancienne à la plus récente, avec leur coût réel."""
    mouvements = (MouvementStock.objects
                  .filter(type_mouvement='sortie', facture__isnull=False)
                  .select_related('medicament')
                  .prefetch_related('lots_servis__lot')
                  .order_by('date'))
    if depuis:
        mouvements = mouvements.filter(date__gte=debut_de_journee(depuis))

    resultat = []
    for mouvement in mouvements:
        prix = mouvement.prix_unitaire or Decimal('0')
        quantite_connue, cout = 0, Decimal('0')
        for sortie in mouvement.lots_servis.all():
            if sortie.lot.prix_achat:
                quantite_connue += sortie.quantite
                cout += sortie.quantite * sortie.lot.prix_achat
        sans_prix = max(mouvement.quantite - quantite_connue, 0)
        resultat.append(Vente(
            quantite=mouvement.quantite,
            vendu=mouvement.quantite * prix,
            cout=cout,
            quantite_sans_prix=sans_prix,
            vendu_sans_prix=sans_prix * prix,
            jour=timezone.localtime(mouvement.date).date(),
            medicament=mouvement.medicament,
        ))
    return resultat


def _cumuler(lignes, libelle=''):
    total = Cumul(libelle=libelle)
    for ligne in lignes:
        total.ajouter(ligne)
    return total


def _lundi(jour):
    return jour - timedelta(days=jour.weekday())


def resume(lignes=None, aujourdhui=None):
    """Les totaux du jour, de la semaine (du lundi à aujourd'hui) et du mois."""
    aujourdhui = aujourdhui or timezone.localdate()
    lundi = _lundi(aujourdhui)
    premier = aujourdhui.replace(day=1)
    if lignes is None:
        lignes = ventes(depuis=min(lundi, premier))
    return {
        'jour': _cumuler(l for l in lignes if l.jour == aujourdhui),
        'semaine': _cumuler(l for l in lignes if lundi <= l.jour <= aujourdhui),
        'mois': _cumuler(l for l in lignes if premier <= l.jour <= aujourdhui),
    }


def par_jour(lignes, jours=31, aujourdhui=None):
    """Les derniers jours où quelque chose a été vendu, du plus récent au plus ancien."""
    aujourdhui = aujourdhui or timezone.localdate()
    limite = aujourdhui - timedelta(days=jours - 1)
    dates = sorted({l.jour for l in lignes if limite <= l.jour <= aujourdhui}, reverse=True)
    return [_cumuler((l for l in lignes if l.jour == d), d.strftime('%d/%m/%Y')) for d in dates]


def par_semaine(lignes, semaines=12, aujourdhui=None):
    aujourdhui = aujourdhui or timezone.localdate()
    limite = _lundi(aujourdhui) - timedelta(weeks=semaines - 1)
    lundis = sorted({_lundi(l.jour) for l in lignes if limite <= l.jour <= aujourdhui}, reverse=True)
    return [_cumuler((l for l in lignes if _lundi(l.jour) == lundi),
                     f"Semaine du {lundi.strftime('%d/%m/%Y')}") for lundi in lundis]


def _mois_precedents(aujourdhui, nombre):
    """(année, mois) des `nombre` derniers mois, le plus récent d'abord."""
    annee, mois = aujourdhui.year, aujourdhui.month
    resultat = []
    for _ in range(nombre):
        resultat.append((annee, mois))
        mois -= 1
        if not mois:
            annee, mois = annee - 1, 12
    return resultat


def par_mois(lignes, nombre=12, aujourdhui=None):
    """Les derniers mois, y compris ceux sans vente : un mois à zéro est une information."""
    aujourdhui = aujourdhui or timezone.localdate()
    return [_cumuler((l for l in lignes if (l.jour.year, l.jour.month) == (a, m)),
                     f'{MOIS_FR[m]} {a}') for a, m in _mois_precedents(aujourdhui, nombre)]


def par_medicament(lignes, annee, mois):
    """Ce que chaque médicament a rapporté ce mois-là, du plus rentable au moins rentable."""
    totaux = {}
    for ligne in lignes:
        if (ligne.jour.year, ligne.jour.month) != (annee, mois):
            continue
        total = totaux.get(ligne.medicament.pk)
        if total is None:
            total = totaux[ligne.medicament.pk] = Vente(
                libelle=ligne.medicament.libelle(), medicament=ligne.medicament)
        total.ajouter(ligne)
    return sorted(totaux.values(), key=lambda t: (-t.profit, -t.vendu, t.libelle))


def mois_avec_ventes(lignes, aujourdhui=None):
    """Les mois proposés au choix : ceux qui ont des ventes, et toujours le mois en cours."""
    aujourdhui = aujourdhui or timezone.localdate()
    mois = {(l.jour.year, l.jour.month) for l in lignes} | {(aujourdhui.year, aujourdhui.month)}
    return [{'valeur': f'{a}-{m:02d}', 'libelle': f'{MOIS_FR[m]} {a}'}
            for a, m in sorted(mois, reverse=True)]


def lots_sans_prix():
    """Les lots dont on ne connaît pas le prix d'achat, même déjà épuisés : ils ont été vendus."""
    return Lot.objects.filter(prix_achat=0)


# ── Ce que la pharmacie achète à ses fournisseurs ─────────────────────

@dataclass
class FactureFournisseur:
    """Un achat : une commande reçue, ou une entrée de stock faite sans commande."""
    numero: str
    jour: date
    fournisseur: str
    fournisseur_id: int
    detail: str
    statut: str
    montant: Decimal = Decimal('0')
    prix_manquant: bool = False
    lien: str = ''
    lignes: list = field(default_factory=list)


def factures_fournisseurs():
    """Tous les achats, du plus récent au plus ancien.

    Seul ce qui est arrivé compte : une commande encore en brouillon ne doit rien, et
    une livraison partielle ne compte que pour ce qui a été reçu. Le stock de départ
    (LOT-INITIAL) n'est pas un achat : il était déjà là à la mise en service.
    """
    factures = []
    commandes = (Commande.objects.select_related('fournisseur')
                 .prefetch_related('lignes__medicament'))
    for commande in commandes:
        recues = [l for l in commande.lignes.all() if l.quantite_recue]
        if not recues:
            continue
        factures.append(FactureFournisseur(
            numero=f'CMD-{commande.pk:04d}',
            jour=commande.date_reception or commande.date_commande,
            fournisseur=commande.fournisseur.nom,
            fournisseur_id=commande.fournisseur_id,
            detail=', '.join(f'{l.medicament.nom} × {l.quantite_recue}' for l in recues),
            statut='Reçue' if commande.est_receptionnee() else 'Livraison partielle',
            montant=sum((l.quantite_recue * l.prix_achat for l in recues), Decimal('0')),
            prix_manquant=any(not l.prix_achat for l in recues),
            lien=reverse('pharmacie:commande_detail', args=[commande.pk]),
        ))

    directes = (Lot.objects.filter(commande__isnull=True)
                .exclude(numero=Lot.NUMERO_INITIAL)
                .select_related('medicament', 'fournisseur'))
    for lot in directes:
        factures.append(FactureFournisseur(
            numero=lot.numero or f'LOT-{lot.pk:04d}',
            jour=timezone.localtime(lot.date_entree).date() if lot.date_entree else None,
            fournisseur=lot.fournisseur.nom if lot.fournisseur_id else '',
            fournisseur_id=lot.fournisseur_id,
            detail=f'{lot.medicament.nom} × {lot.quantite_initiale}',
            statut='Entrée sans commande',
            montant=lot.quantite_initiale * lot.prix_achat,
            prix_manquant=not lot.prix_achat,
            lien=f"{reverse('pharmacie:lots')}?medicament={lot.medicament_id}&etat=tous",
        ))
    return sorted(factures, key=lambda f: (f.jour or date.min, f.numero), reverse=True)


def a_reclamer_par_assurance():
    """Ce que chaque assurance doit encore sur les médicaments, sans avoir été réclamé.

    Une ligne par assurance : les anciennes factures Takaful ne doivent pas
    passer pour de l'AMO.
    """
    from facturation.models import Facture
    lignes = (Facture.objects
              .filter(ordonnance__isnull=False, assurance__isnull=False,
                      taux_prise_en_charge__gt=0, statut_assurance='a_reclamer')
              .values('assurance__nom')
              .annotate(montant=Sum('montant_assurance'))
              .order_by('-montant'))
    return [{'nom': l['assurance__nom'], 'montant': l['montant']}
            for l in lignes if l['montant']]
