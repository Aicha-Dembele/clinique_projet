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
(voir pharmacie.views._facture_pour_dispensation). Elle se règle aussi
ailleurs — au comptoir de la pharmacie et non à la réception : voir la
section « Qui encaisse quoi » plus bas.

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


# ── Qui encaisse quoi : deux caisses séparées ────────────────────
#
# Les médicaments se règlent AU COMPTOIR DE LA PHARMACIE, chez le pharmacien
# qui vient de les servir. Tout le reste — consultation, examen,
# hospitalisation — se règle À LA RÉCEPTION. Une réceptionniste n'encaisse
# donc pas une ordonnance, et un pharmacien n'encaisse pas une consultation.

CAISSE_PHARMACIE = 'pharmacie'
CAISSE_RECEPTION = 'reception'

CAISSE_LIBELLES = {
    CAISSE_PHARMACIE: 'la pharmacie',
    CAISSE_RECEPTION: 'la réception',
}

#: Caisses que chaque rôle est habilité à tenir.
CAISSES_PAR_ROLE = {
    'pharmacien':     {CAISSE_PHARMACIE},
    'receptionniste': {CAISSE_RECEPTION},
    # L'administrateur garde l'accès aux deux : il n'encaisse pas au
    # quotidien, mais il doit pouvoir rattraper une erreur de caisse.
    'admin':          {CAISSE_PHARMACIE, CAISSE_RECEPTION},
}


def caisse_de(facture):
    """À quelle caisse cette facture se règle-t-elle ?"""
    return CAISSE_PHARMACIE if facture.ordonnance_id else CAISSE_RECEPTION


def caisses_du_role(role):
    """Les caisses que ce rôle peut tenir (ensemble vide s'il n'en tient aucune)."""
    return CAISSES_PAR_ROLE.get(role, set())


def factures_de_la_caisse(requete, role):
    """Restreint une liste de factures à celles que ce rôle peut encaisser."""
    caisses = caisses_du_role(role)
    if CAISSE_PHARMACIE in caisses and CAISSE_RECEPTION in caisses:
        return requete
    if CAISSE_PHARMACIE in caisses:
        return requete.filter(ordonnance__isnull=False)
    if CAISSE_RECEPTION in caisses:
        return requete.filter(ordonnance__isnull=True)
    return requete.none()


def peut_encaisser(facture, role):
    """Ce rôle tient-il la caisse où cette facture se règle ?

    Sert à décider où emmener quelqu'un après avoir créé un acte payant :
    on ne l'envoie à la caisse que s'il EST la caisse. Un médecin qui
    prescrit un examen doit rester dans son travail — la facture qu'il vient
    de déclencher se règle à la réception, pas chez lui.
    """
    return blocage_caisse(facture, role) is None


def blocage_caisse(facture, role):
    """None si ce rôle peut encaisser cette facture, sinon le message de refus.

    À appeler côté serveur avant d'enregistrer un paiement : la liste
    déroulante ne propose déjà que les bonnes factures, mais un formulaire
    peut toujours être renvoyé avec un numéro forcé.
    """
    caisse = caisse_de(facture)
    if caisse in caisses_du_role(role):
        return None
    return (f"FAC-{facture.pk:04d} se règle à {CAISSE_LIBELLES[caisse]}, "
            f"pas ici. Les médicaments s'encaissent au comptoir de la "
            f"pharmacie, les soins à la réception.")


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
