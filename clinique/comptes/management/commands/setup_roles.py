"""Initialise les rôles, les permissions et un compte administrateur par défaut.

La liste des rôles et de leurs permissions vit dans `comptes/roles.py` : c'est
la même source que celle utilisée par les tests, pour qu'ils vérifient bien les
droits réels de la clinique et pas des rôles inventés pour l'occasion.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from comptes.models import Profil
from comptes.roles import installer_roles


class Command(BaseCommand):
    help = "Initialise les roles, permissions et un compte administrateur par defaut"

    def add_arguments(self, parser):
        parser.add_argument('--database', default='default',
                            help="Base à initialiser (« default » ou « sqlite »).")

    def handle(self, *args, **options):
        db = options['database']

        self.stdout.write("Creation des permissions et des roles...")
        roles = installer_roles(db)

        self.stdout.write("Creation du compte admin par defaut (admin / admin123)...")
        user, created = User.objects.using(db).get_or_create(
            username='admin',
            defaults={'is_staff': True, 'is_superuser': True,
                      'first_name': 'Super', 'last_name': 'Admin'},
        )
        if created:
            user.set_password('admin123')
            user.save(using=db)
        Profil.objects.using(db).get_or_create(
            user=user, defaults={'role': roles['admin']})

        self.stdout.write(self.style.SUCCESS("Setup termine."))
