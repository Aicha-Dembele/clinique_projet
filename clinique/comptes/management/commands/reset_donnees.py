"""
Remise à zéro des données médicales de la clinique.

Efface les données d'activité (patients, consultations, ordonnances,
traitements, hospitalisations, factures, mouvements de stock…) et remet
les compteurs d'identifiants à 1, pour repartir sur une base vierge.

CONSERVE volontairement :
  - les comptes de connexion, profils, rôles et permissions ;
  - les fiches du personnel (médecins, infirmiers, laborantins…) ;
  - les catalogues de référence : médicaments, spécialités, tarifs,
    assurances.

Usage :
    python manage.py reset_donnees                      # demande confirmation
    python manage.py reset_donnees --force              # sans confirmation
    python manage.py reset_donnees --database sqlite    # sur db.sqlite3

Sur le poste de développement, local_settings.py définit deux bases :
« default » (MySQL/XAMPP, celle qu'utilise l'application) et « sqlite »
(db.sqlite3, la copie déployée en ligne). Sur le serveur PythonAnywhere,
seule « default » existe et pointe vers db.sqlite3.
"""

from django.core.management.base import BaseCommand
from django.db import connections, transaction

from comptes.models import JournalAudit, Notification
from consultation.models import (
    AdministrationTraitement,
    AssistanceInfirmier,
    Consultation,
    DossierMedical,
    ExamenMedical,
    Hospitalisation,
    Ordonnance,
    Rendez_vous,
    ResultatExamen,
    Traitement,
)
from facturation.models import Facture, LigneFacture, Paiement
from patients.models import Patient
from pharmacie.models import MouvementStock

# Ordre volontaire : des feuilles vers les racines, pour que rien ne
# disparaisse par cascade avant d'avoir été compté.
MODELES_A_VIDER = [
    Paiement,
    LigneFacture,
    Facture,
    MouvementStock,
    AdministrationTraitement,
    AssistanceInfirmier,
    Ordonnance,
    Traitement,
    ResultatExamen,
    ExamenMedical,
    Hospitalisation,
    Consultation,
    Rendez_vous,
    DossierMedical,
    Notification,
    JournalAudit,
    Patient,
]


class Command(BaseCommand):
    help = "Vide les données médicales et remet les identifiants à 1."

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help="Ne pas demander de confirmation (usage non interactif).",
        )
        parser.add_argument(
            '--database',
            default='default',
            help="Alias de la base à vider (défaut : « default »).",
        )

    def handle(self, *args, **options):
        db = options['database']
        if db not in connections:
            raise SystemExit(
                "Base « %s » inconnue. Disponibles : %s"
                % (db, ', '.join(connections))
            )

        avant = {m.__name__: m.objects.using(db).count() for m in MODELES_A_VIDER}
        total = sum(avant.values())

        self.stdout.write(
            "\nBase ciblée : %s (%s)" % (db, connections[db].settings_dict['NAME'])
        )
        self.stdout.write("À supprimer :")
        for nom, n in avant.items():
            if n:
                self.stdout.write("  %-26s %4d" % (nom, n))
        self.stdout.write(self.style.WARNING("  TOTAL : %d enregistrements" % total))

        if not options['force']:
            reponse = input("\nConfirmer la suppression ? (oui/non) : ")
            if reponse.strip().lower() not in ('oui', 'o', 'yes', 'y'):
                self.stdout.write(self.style.ERROR("Annulé, rien n'a été supprimé."))
                return

        tables = []
        with transaction.atomic(using=db):
            for modele in MODELES_A_VIDER:
                modele.objects.using(db).all().delete()
                tables.append(modele._meta.db_table)
                # Tables de liaison (ManyToMany) du modèle, ex. le partage
                # d'un dossier médical entre médecins.
                for champ in modele._meta.many_to_many:
                    tables.append(champ.remote_field.through._meta.db_table)

            self._remettre_compteurs(db, tables)

        apres = sum(m.objects.using(db).count() for m in MODELES_A_VIDER)
        self.stdout.write(
            self.style.SUCCESS(
                "\n%d enregistrements supprimés. Il en reste %d.\n"
                "Les compteurs sont remis à zéro : le prochain patient "
                "enregistré portera l'identifiant 1." % (total, apres)
            )
        )

    def _remettre_compteurs(self, db, tables):
        """Remet les séquences d'auto-incrément à zéro."""
        connection = connections[db]

        if connection.vendor == 'mysql':
            # MySQL n'a pas de sqlite_sequence : on remet AUTO_INCREMENT à 1
            # table par table.
            with connection.cursor() as cur:
                for table in set(tables):
                    cur.execute("ALTER TABLE `%s` AUTO_INCREMENT = 1" % table)
            self.stdout.write("Compteurs AUTO_INCREMENT remis à 1 (MySQL).")
            return

        if connection.vendor != 'sqlite':
            self.stdout.write(
                self.style.WARNING(
                    "Base %s : compteurs non réinitialisés." % connection.vendor
                )
            )
            return

        with connection.cursor() as cur:
            cur.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='sqlite_sequence'"
            )
            if not cur.fetchone():
                return
            for table in set(tables):
                cur.execute("DELETE FROM sqlite_sequence WHERE name = %s", [table])
