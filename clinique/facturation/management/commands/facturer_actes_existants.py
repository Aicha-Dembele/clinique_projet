"""
Mise en conformité avec le paiement d'avance : facture les actes déjà en base.

La clinique facture désormais la consultation, l'examen et l'hospitalisation
AVANT de les réaliser (voir facturation/regles.py) : la facture est créée
automatiquement dès que l'acte est enregistré. Les actes saisis avant ce
changement n'ont pas de facture — le médecin ne pourrait donc plus enregistrer
leur consultation, ni le laborantin saisir leur résultat.

Cette commande crée la facture manquante de chaque acte, au tarif en vigueur,
avec l'assurance du patient appliquée. Elle ne touche pas aux actes qui ont
déjà une facture, et n'encaisse rien : les factures créées sont « non payé »,
à charge de la réception de les recouvrer.

Les rendez-vous ANNULÉS sont laissés de côté : il n'y a rien à facturer.

Usage :
    python manage.py facturer_actes_existants --dry-run           # simulation
    python manage.py facturer_actes_existants                     # confirmation demandée
    python manage.py facturer_actes_existants --force             # sans confirmation
    python manage.py facturer_actes_existants --database sqlite   # sur db.sqlite3

Comme `decouper_factures`, la commande doit être passée sur les deux bases du
poste de développement (« default » = MySQL, « sqlite » = la copie déployée).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from facturation.regles import creer_facture, fcfa


class Command(BaseCommand):
    help = ("Crée la facture manquante des rendez-vous, examens et "
            "hospitalisations enregistrés avant le passage au paiement d'avance.")

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Simulation : affiche ce qui serait créé, sans rien écrire.")
        parser.add_argument('--force', action='store_true',
                            help="Ne pas demander de confirmation.")
        parser.add_argument('--database', default='default',
                            help="Base à traiter (« default » ou « sqlite »).")

    def handle(self, *args, **options):
        from consultation.models import Rendez_vous, ExamenMedical, Hospitalisation

        base = options['database']
        simulation = options['dry_run']

        # (lien sur la facture, libellé, actes sans facture)
        chantiers = [
            ('rendez_vous', 'Consultation (rendez-vous)',
             Rendez_vous.objects.using(base)
             .exclude(statut='annule').filter(facture__isnull=True)
             .select_related('patient__assurance', 'medecin')),
            ('examen', 'Examen médical',
             ExamenMedical.objects.using(base)
             .filter(facture__isnull=True).select_related('patient__assurance')),
            ('hospitalisation', 'Hospitalisation',
             Hospitalisation.objects.using(base)
             .filter(facture__isnull=True).select_related('patient__assurance')),
        ]

        chantiers = [(lien, libelle, list(qs)) for lien, libelle, qs in chantiers]
        total = sum(len(actes) for _, _, actes in chantiers)

        if not total:
            self.stdout.write(self.style.SUCCESS(
                f"[{base}] Rien à faire : tous les actes ont déjà leur facture."))
            return

        self.stdout.write(f"\n[{base}] Actes sans facture :")
        for _, libelle, actes in chantiers:
            if actes:
                self.stdout.write(f"  · {libelle} : {len(actes)}")

        if simulation:
            self.stdout.write(self.style.WARNING(
                f"\nSimulation — {total} facture(s) seraient créées. Rien n'a été écrit."))
            return

        if not options['force']:
            reponse = input(f"\nCréer {total} facture(s) sur la base « {base} » ? [o/N] ")
            if reponse.strip().lower() not in ('o', 'oui', 'y', 'yes'):
                self.stdout.write(self.style.WARNING("Annulé — rien n'a été écrit."))
                return

        cree = 0
        montant = 0
        with transaction.atomic(using=base):
            for lien, libelle, actes in chantiers:
                for acte in actes:
                    facture = creer_facture(acte.patient, lien, acte)
                    cree += 1
                    montant += facture.part_patient()
                    self.stdout.write(
                        f"  FAC-{facture.pk:04d} — {libelle} — {acte.patient} — "
                        f"{fcfa(facture.part_patient())} à encaisser")

        self.stdout.write(self.style.SUCCESS(
            f"\n[{base}] {cree} facture(s) créée(s) — {fcfa(montant)} à encaisser au total."))
