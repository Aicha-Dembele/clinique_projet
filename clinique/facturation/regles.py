"""Règle de la clinique : on paie avant d'être soigné.

Trois actes sont PRÉPAYÉS — la consultation, l'examen médical et
l'hospitalisation. Pour chacun, deux moments distincts :

    ┌ enregistrement de l'acte ──────────┬ réalisation de l'acte ─────────────┐
    │ la facture est créée automatiquement│ interdite tant qu'elle n'est pas   │
    │ au tarif en vigueur                 │ soldée par le patient              │
    ├─────────────────────────────────────┼────────────────────────────────────┤
    │ la réception fixe le rendez-vous    │ le médecin enregistre la           │
    │                                     │ consultation                       │
    │ le médecin prescrit l'examen        │ le laborantin saisit le résultat   │
    │ le médecin enregistre l'admission   │ le patient est admis en chambre    │
    └─────────────────────────────────────┴────────────────────────────────────┘

La PHARMACIE fait exception : le montant n'est connu qu'une fois les
médicaments servis, sa facture est donc créée APRÈS la dispensation
(voir pharmacie.views._facture_pour_dispensation).

« Soldée » veut dire : toute la part patient encaissée. La part prise en charge
par l'assurance n'est pas exigée au guichet, elle reste une créance sur
l'assureur — un patient couvert à 100 % n'a donc rien à payer et n'est jamais
bloqué.
"""

from .models import Facture


# Actes prépayés : nom du champ de Facture → désignation lisible de l'acte,
# utilisée telle quelle dans les messages d'erreur.
ACTES_PREPAYES = {
    'rendez_vous':     'la consultation',
    'examen':          "l'examen",
    'hospitalisation': "l'hospitalisation",
}


def fcfa(montant):
    """Montant lisible, séparateur de milliers en espace : « 12 500 FCFA »."""
    try:
        return f"{int(montant):,}".replace(',', ' ') + ' FCFA'
    except (TypeError, ValueError):
        return '0 FCFA'


# ── Retrouver la facture d'un acte ───────────────────────────────

def _db(acte):
    """Base d'où vient l'acte : la facture doit être lue et écrite au même
    endroit (le poste de développement a MySQL *et* la copie SQLite déployée)."""
    etat = getattr(acte, '_state', None)
    return getattr(etat, 'db', None) or 'default'


def facture_de(lien, acte):
    """Facture rattachée à cet acte, ou None.

    `lien` est le nom du champ de Facture : 'rendez_vous', 'examen' ou
    'hospitalisation'. On prend la dernière créée : en cas de doublon
    accidentel, c'est celle-là qui fait foi.
    """
    if acte is None or acte.pk is None:
        return None
    return (Facture.objects.using(_db(acte))
            .filter(**{lien: acte}).order_by('-pk').first())


def factures_par_acte(lien, actes):
    """{id de l'acte : facture} pour toute une liste d'actes, en UNE requête.

    Sert aux listes et aux menus déroulants : sans cela, afficher l'état de
    paiement de 50 rendez-vous coûterait 50 requêtes (N+1).
    """
    actes = [a for a in actes if a.pk]
    if not actes:
        return {}
    ids = [a.pk for a in actes]
    factures = (Facture.objects.using(_db(actes[0]))
                .filter(**{f'{lien}_id__in': ids})
                .prefetch_related('paiements').order_by('pk'))
    return {getattr(f, f'{lien}_id'): f for f in factures}


# ── Établir / mettre à jour la facture d'un acte ─────────────────

def creer_facture(patient, lien, acte):
    """Établit la facture d'un acte prépayé, si elle n'existe pas déjà.

    Le prix vient de la grille des tarifs et l'assurance du patient est
    appliquée d'office : la réception n'a plus qu'à encaisser. Renvoie la
    facture (nouvelle ou existante).
    """
    facture = facture_de(lien, acte)
    if facture is not None:
        return facture
    facture = Facture(patient=patient, assurance=patient.assurance)
    setattr(facture, lien, acte)
    facture.save(using=_db(acte))   # génère les lignes, calcule total et statut
    return facture


def recalculer_facture(lien, acte):
    """Remet la facture au tarif courant après modification de l'acte.

    Nécessaire quand ce qui détermine le prix change : spécialité du médecin
    du rendez-vous, type d'examen, type de chambre ou nombre de nuits. Si le
    montant augmente, la facture repasse d'elle-même en « partiel » et l'acte
    est de nouveau bloqué jusqu'au complément. Renvoie None s'il n'y a pas
    (encore) de facture.
    """
    facture = facture_de(lien, acte)
    if facture is not None:
        facture.save(using=_db(acte))
    return facture


def facturer(patient, lien, acte):
    """Garantit une facture à jour pour cet acte : la crée, ou la recalcule.

    C'est l'appel à utiliser après l'enregistrement OU la modification d'un
    acte prépayé, sans avoir à savoir lequel des deux cas on est.
    """
    return recalculer_facture(lien, acte) or creer_facture(patient, lien, acte)


# ── Autoriser (ou refuser) la réalisation de l'acte ──────────────

def blocage(lien, acte):
    """None si l'acte peut être réalisé, sinon le message expliquant le refus.

    À appeler côté serveur avant tout enregistrement : les menus déroulants
    grisent déjà les actes non réglés, mais un formulaire peut toujours être
    renvoyé avec une valeur forcée, et la facture peut avoir changé entre
    l'affichage de la page et sa validation.
    """
    nom = ACTES_PREPAYES.get(lien, "cet acte")
    facture = facture_de(lien, acte)

    if facture is None:
        return (f"Aucune facture n'a été établie pour {nom}. "
                f"À la clinique Nevroglie, {nom} se règle d'avance : "
                f"passez d'abord par la réception.")

    if not facture.est_reglee():
        return (f"FAC-{facture.pk:04d} n'est pas réglée — il reste "
                f"{fcfa(facture.montant_restant())} à encaisser sur "
                f"{fcfa(facture.part_patient())} à la charge du patient. "
                f"{nom.capitalize()} ne peut pas être réalisé avant le paiement.")

    return None


def etat_paiement(facture):
    """Petit résumé de l'état de paiement d'un acte, pour les listes et les
    menus déroulants. `facture` peut être None (acte non encore facturé)."""
    if facture is None:
        return {'facture': None, 'reglee': False, 'code': 'sans_facture',
                'libelle': 'Non facturé', 'reste': None}
    if facture.est_reglee():
        return {'facture': facture, 'reglee': True, 'code': 'payee',
                'libelle': f'Réglé — FAC-{facture.pk:04d}', 'reste': None}
    reste = facture.montant_restant()
    return {'facture': facture, 'reglee': False, 'code': 'impayee',
            'libelle': f'À régler — {fcfa(reste)}', 'reste': reste}
