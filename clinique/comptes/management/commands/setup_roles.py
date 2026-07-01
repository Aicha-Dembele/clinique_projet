from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from comptes.models import Role, Permission, Profil


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
    ('tarif.manage', 'Gerer les tarifs'),

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
        'examen.view', 'examen.realiser', 'examen.change',
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
        'tarif.view',
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


class Command(BaseCommand):
    help = "Initialise les roles, permissions et un compte administrateur par defaut"

    def handle(self, *args, **options):
        self.stdout.write("Creation des permissions...")
        perm_objs = {}
        for code, libelle in PERMISSIONS:
            obj, _ = Permission.objects.update_or_create(
                code=code, defaults={'libelle': libelle})
            perm_objs[code] = obj

        self.stdout.write("Creation des roles...")
        for role_code, libelle in ROLE_LIBELLES.items():
            role, _ = Role.objects.update_or_create(
                code=role_code, defaults={'libelle': libelle})
            perms = ROLE_PERMISSIONS[role_code]
            if perms == '*':
                role.permissions.set(perm_objs.values())
            else:
                role.permissions.set([perm_objs[p] for p in perms if p in perm_objs])

        self.stdout.write("Creation du compte admin par defaut (admin / admin123)...")
        admin_role = Role.objects.get(code='admin')
        user, created = User.objects.get_or_create(
            username='admin',
            defaults={'is_staff': True, 'is_superuser': True, 'first_name': 'Super', 'last_name': 'Admin'},
        )
        if created:
            user.set_password('admin123')
            user.save()
        Profil.objects.get_or_create(user=user, defaults={'role': admin_role})

        self.stdout.write(self.style.SUCCESS("Setup termine."))
