"""Le client de l'API de paiement SAMA Money — l'appel, et rien d'autre.

Ce fichier ne connaît ni Django ni la base : on lui donne un numéro et un
montant, il parle à SAMA Money et rend un résultat. C'est la vue qui décide
quoi en faire. On peut donc le tester sans réseau et sans base.

Documentation : https://developer.sama.money
  POST /v1/charges            crée l'encaissement
  GET  /v1/charges/{ref}      relit son statut

Le patient confirme depuis son application SAMA, ou en composant #600#.
Tant qu'il n'a pas confirmé, l'encaissement reste `pending` : le paiement
n'est enregistré en base que lorsqu'il passe à `succeeded`.

MODE DÉMONSTRATION
Sans clé API configurée, le client n'appelle personne et rend des réponses
fabriquées. La soutenance peut donc se faire sans réseau et sans compte.
Le jour où la clé de production est posée dans `local_settings.py`, le même
code appelle le vrai service — il n'y a rien à réécrire.
"""

import uuid

import requests
from django.conf import settings

#: Adresse de l'API. Surchargeable dans local_settings.py pour viser un
#: autre environnement.
BASE_URL = getattr(settings, 'SAMA_MONEY_BASE_URL', 'https://api.sama.money/v1')

#: Au-delà, on abandonne : la caisse ne peut pas rester bloquée sur un
#: service qui ne répond pas pendant que le patient attend au guichet.
DELAI = 15

#: Les statuts que l'API peut renvoyer (documentation SAMA).
EN_ATTENTE = 'pending'
REUSSI = 'succeeded'
ECHOUE = 'failed'
EXPIRE = 'expired'

#: Numéro qui échoue volontairement en mode démonstration, pour montrer au
#: jury que le refus est géré et pas seulement le cas qui marche.
NUMERO_REFUS_DEMO = '00000000'


class ErreurSama(Exception):
    """L'encaissement n'a pas pu être demandé : réseau, clé, ou refus de l'API.

    Le message est destiné à être montré à la caisse, pas au patient.
    """


def cle_api():
    """La clé configurée, ou une chaîne vide si on tourne en démonstration."""
    return getattr(settings, 'SAMA_MONEY_CLE_API', '') or ''


def mode_demonstration():
    """Vrai tant qu'aucune clé n'est configurée."""
    return not cle_api()


def _entetes(cle_idempotence=None):
    """Les en-têtes de chaque appel.

    `Idempotency-Key` est recommandé par SAMA : si le réseau coupe et qu'on
    rejoue la requête, le patient n'est pas débité deux fois.
    """
    entetes = {
        'Authorization': f'Bearer {cle_api()}',
        'Content-Type': 'application/json',
    }
    if cle_idempotence:
        entetes['Idempotency-Key'] = cle_idempotence
    return entetes


def _appeler(methode, chemin, **kwargs):
    """Un appel HTTP à l'API, avec les erreurs traduites en ErreurSama."""
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    try:
        reponse = requests.request(methode, url, timeout=DELAI, **kwargs)
    except requests.Timeout:
        raise ErreurSama(
            "SAMA Money n'a pas répondu dans les temps. Le paiement n'a pas "
            "été enregistré : réessayez, ou encaissez en espèces.")
    except requests.RequestException as erreur:
        raise ErreurSama(f"SAMA Money est injoignable ({erreur}).")

    try:
        corps = reponse.json()
    except ValueError:
        raise ErreurSama(
            f"Réponse illisible de SAMA Money (code {reponse.status_code}).")

    if reponse.status_code >= 400:
        detail = (corps.get('error') or {}).get('code') or reponse.status_code
        raise ErreurSama(f"SAMA Money a refusé la demande ({detail}).")
    return corps


def demander_encaissement(numero, montant_fcfa, description='', reference=''):
    """POST /v1/charges — demande au patient de confirmer le paiement.

    Rend le dictionnaire de l'encaissement. Son `status` vaut `pending` :
    l'argent n'a pas encore bougé, le patient doit confirmer.
    """
    numero = ''.join(c for c in str(numero) if c.isdigit())
    montant = int(montant_fcfa)

    if len(numero) < 8:
        raise ErreurSama("Numéro SAMA Money invalide — au moins 8 chiffres.")
    if montant <= 0:
        raise ErreurSama("Le montant doit être supérieur à zéro.")

    if mode_demonstration():
        return _encaissement_fictif(numero, montant, description, reference)

    return _appeler(
        'POST', 'charges',
        headers=_entetes(cle_idempotence=str(uuid.uuid4())),
        json={
            'client_phone': numero,
            'amount_xof': montant,
            'description': description[:140],
            'reference': reference,
        },
    )


def lire_encaissement(reference):
    """GET /v1/charges/{reference} — où en est la confirmation du patient ?

    À relire après la notification, et aussi en rattrapage : une notification
    peut se perdre, le statut lu ici fait foi.
    """
    if mode_demonstration():
        return _relecture_fictive(reference)
    return _appeler('GET', f'charges/{reference}', headers=_entetes())


# ─────────────────────────────────────────────────────────────────
#  Mode démonstration : aucune requête ne part
# ─────────────────────────────────────────────────────────────────

#: Marqueur glissé dans la référence fictive quand la démonstration doit
#: refuser. Le sort de l'encaissement est ainsi décidé ici, et la vue n'a
#: aucune règle de démonstration à connaître : elle suit le statut, comme
#: elle le fera avec le vrai service.
_MARQUE_REFUS = 'refus'


def _encaissement_fictif(numero, montant, description, reference):
    """Une réponse de la même forme que celle de l'API, fabriquée ici."""
    sort = _MARQUE_REFUS if numero == NUMERO_REFUS_DEMO else 'ok'
    return {
        'reference': f'chg_demo_{sort}_{uuid.uuid4().hex[:12]}',
        'object': 'charge',
        'mode': 'demonstration',
        'amount_xof': montant,
        'currency': 'XOF',
        'client_phone': numero,
        'status': EN_ATTENTE,
        'description': description,
        'partner_reference': reference,
        'error_message': None,
    }


def _relecture_fictive(reference):
    """En démonstration, le patient confirme — sauf s'il a tapé le numéro de refus."""
    refuse = f'_{_MARQUE_REFUS}_' in reference
    return {
        'reference': reference,
        'object': 'charge',
        'mode': 'demonstration',
        'status': ECHOUE if refuse else REUSSI,
        'error_message': 'Paiement refusé par le client.' if refuse else None,
    }
