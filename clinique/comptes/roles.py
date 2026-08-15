"""Rôles et permissions de référence de la clinique.

Source unique de vérité : la commande `manage.py setup_roles` s'en sert pour
initialiser une base, et les tests pour recréer les rôles réels au lieu d'en
inventer des vides — sans quoi un test se heurte à `permission_required` et
reçoit une redirection au lieu de la page.
"""

from .models import Role, Permission


PERMISSIONS = [
    ('patient.view', 'Consulter les patients'),
    ('patient.add', 'Enregistrer un patient'),
    ('patient.change', 'Modifier un patient'),
    ('patient.delete', 'Supprimer un patient'),

    ('dossier.view', 'Consulter un dossier medical'),
    ('dossier.add', 'Creer un dossier medical'),

    ('rdv.view', 'Consulter les rendez-vous'),
    ('rdv.add', 'Organiser un rendez-vous'),
    ('rdv.change', 'Modifier un rendez-vous'),
    ('rdv.delete', 'Supprimer un rendez-vous'),

    ('consultation.view', 'Consulter les consultations'),
    ('consultation.add', 'Realiser une consultation'),
    ('consultation.change', 'Modifier une consultation'),
    ('consultation.delete', 'Supprimer une consultation'),

    ('diagnostic.add', 'Poser un diagnostic'),
    ('ordonnance.view', 'Consulter les ordonnances'),
    ('ordonnance.add', 'Prescrire une ordonnance'),
    ('ordonnance.delete', 'Supprimer une ordonnance'),

    ('examen.view', 'Consulter les examens'),
    ('examen.demander', 'Demander un examen'),
    ('examen.realiser', 'Realiser un examen'),
    ('examen.change', 'Modifier un examen'),
    ('examen.delete', 'Supprimer un examen'),

    ('resultat.view', 'Consulter les resultats'),
    ('resultat.add', 'Enregistrer des resultats'),
    ('resultat.transmettre', 'Transmettre les resultats au medecin'),

    ('traitement.view', 'Consulter les traitements'),
    ('traitement.add', 'Prescrire un traitement'),
    ('traitement.administrer', 'Administrer un traitement'),

    ('hospitalisation.view', 'Consulter les hospitalisations'),
    ('hospitalisation.add', 'Gerer une hospitalisation'),
    ('hospitalisation.change', 'Modifier une hospitalisation'),
    ('hospitalisation.delete', 'Supprimer une hospitalisation'),

    ('facture.view', 'Consulter les factures'),
    ('facture.add', 'Generer une facture'),
    ('facture.change', 'Modifier une facture'),
    ('facture.delete', 'Supprimer une facture'),

    ('paiement.view', 'Consulter les paiements'),
    ('paiement.add', 'Enregistrer un paiement'),
    ('paiement.change', 'Modifier un paiement'),
    ('paiement.delete', 'Supprimer un paiement'),

    ('tarif.view', 'Consulter les tarifs'),
    ('tarif.add', 'Ajouter un tarif'),
    ('tarif.manage', 'Gerer les tarifs (modifier, supprimer)'),

    ('pharmacie.view', 'Consulter la pharmacie et le stock'),
    ('medicament.manage', 'Gerer les medicaments (catalogue)'),
    ('stock.entree', 'Enregistrer une entree de stock'),
    ('stock.sortie', 'Dispenser un medicament (sortie de stock)'),

    ('user.manage', 'Gerer les utilisateurs'),
    ('role.manage', 'Gerer les roles et permissions'),
    ('rapport.view', 'Consulter les rapports'),
]


ROLE_PERMISSIONS = {
    'admin': '*',
    'medecin': [
        'patient.view',
        'dossier.view', 'dossier.add',
        'rdv.view',
        'consultation.view', 'consultation.add', 'consultation.change',
        'diagnostic.add',
        'ordonnance.view', 'ordonnance.add', 'ordonnance.delete',
        'examen.view', 'examen.demander',
        'resultat.view',
        'traitement.view', 'traitement.add',
        'hospitalisation.view', 'hospitalisation.add',
    ],
    'laborantin': [
        'patient.view',
        # Le laborantin consulte l'examen que le médecin lui transmet (examen.view)
        # et le réalise (examen.realiser) ; il ne peut PAS le modifier.
        'examen.view', 'examen.realiser',
        'resultat.view', 'resultat.add', 'resultat.transmettre',
    ],
    'infirmier': [
        'patient.view',
        'dossier.view',
        'consultation.view',
        'traitement.view', 'traitement.administrer',
        'hospitalisation.view',
    ],
    'receptionniste': [
        'patient.view', 'patient.add', 'patient.change',
        'rdv.view', 'rdv.add', 'rdv.change', 'rdv.delete',
        'hospitalisation.view', 'hospitalisation.add', 'hospitalisation.change',
        'facture.view', 'facture.add', 'facture.change',
        'paiement.view', 'paiement.add', 'paiement.change',
        'tarif.view', 'tarif.add',
        'pharmacie.view', 'medicament.manage', 'stock.entree', 'stock.sortie',
    ],
    'pharmacien': [
        'patient.view',
        'ordonnance.view',
        'traitement.view',
        'pharmacie.view', 'medicament.manage',
        'stock.entree', 'stock.sortie',
        'facture.view',
    ],
}


ROLE_LIBELLES = {
    'admin': 'Administrateur',
    'medecin': 'Medecin',
    'laborantin': 'Laborantin',
    'infirmier': 'Infirmier',
    'receptionniste': 'Receptionniste',
    'pharmacien': 'Pharmacien',
}


def installer_roles(db='default'):
    """Crée (ou met à jour) les permissions et les rôles de référence.

    Idempotent : relançable sans risque. Renvoie {code du rôle: Role}.
    `db` permet de viser la copie SQLite du déploiement comme la base MySQL.
    """
    perms = {}
    for code, libelle in PERMISSIONS:
        perms[code], _ = Permission.objects.using(db).update_or_create(
            code=code, defaults={'libelle': libelle})

    roles = {}
    for code, libelle in ROLE_LIBELLES.items():
        role, _ = Role.objects.using(db).update_or_create(
            code=code, defaults={'libelle': libelle})
        accordees = ROLE_PERMISSIONS[code]
        role.permissions.set(
            perms.values() if accordees == '*'
            else [perms[p] for p in accordees if p in perms])
        roles[code] = role
    return roles
