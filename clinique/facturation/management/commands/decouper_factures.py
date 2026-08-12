"""
Découpage des anciennes factures groupées, une facture par service.

Historiquement, une facture regroupait la consultation, les examens prescrits
pendant celle-ci, l'hospitalisation et les médicaments de l'ordonnance. La
règle est désormais : **un service = une facture**, chacune avec sa propre
prise en charge par l'assurance.

Cette commande met l'existant en conformité :
  - la facture d'origine est CONSERVÉE et ne garde qu'un seul service
    (la consultation en priorité, sinon l'hospitalisation, sinon l'examen,
    sinon l'ordonnance) ;
  - une nouvelle facture est créée pour chacun des autres services, en
    reprenant le patient, l'assurance et le taux de prise en charge ;
  - les paiements déjà encaissés restent sur la facture d'origine.

Usage :
    python manage.py decouper_factures --dry-run           # simulation, n'écrit rien
    python manage.py decouper_factures                     # demande confirmation
    python manage.py decouper_factures --force             # sans confirmation
    python manage.py decouper_factures --database sqlite   # sur db.sqlite3

Comme `reset_donnees`, la commande doit être passée sur les deux bases du
poste de développement (« default » = MySQL, « sqlite » = la copie déployée).
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from facturation.models import Facture


class Command(BaseCommand):
    help = "Découpe les factures groupées en une facture par service (consultation, examen, hospitalisation, ordonnance)."

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help="Ne pas demander de confirmation.")
        parser.add_argument('--dry-run', action='store_true',
                            help="Simuler : afficher le découpage sans rien écrire.")
        parser.add_argument('--database', default='default',
                            help="Base de données à traiter (default ou sqlite).")

    # ── Analyse ──────────────────────────────────────────────────
    def _services_de(self, facture, db):
        """Liste des (code, objet) que cette facture couvre aujourd'hui.

        On repart des liens de la facture ET des lignes réellement présentes :
        les examens n'avaient pas de lien propre avant, ils étaient déduits de
        la consultation.
        """
        services = []

        if facture.consultation_id:
            services.append(('consultation', facture.consultation))
            # Les examens de cette consultation étaient factures avec elle.
            for examen in (facture.consultation.examenmedical_set
                           .using(db).all().order_by('pk')):
                services.append(('examen', examen))

        if facture.hospitalisation_id:
            services.append(('hospitalisation', facture.hospitalisation))

        # Médicaments : une facture par ordonnance dispensée.
        from pharmacie.models import MouvementStock
        ordo_ids = (MouvementStock.objects.using(db)
                    .filter(facture_id=facture.pk, type_mouvement='sortie',
                            ordonnance__isnull=False)
                    .values_list('ordonnance_id', flat=True).distinct())
        if ordo_ids:
            from consultation.models import Ordonnance
            for ordo in Ordonnance.objects.using(db).filter(pk__in=list(ordo_ids)).order_by('pk'):
                services.append(('ordonnance', ordo))

        return services

    # ── Exécution ────────────────────────────────────────────────
    def handle(self, *args, **options):
        db = options['database']
        dry = options['dry_run']

        factures = list(Facture.objects.using(db)
                        .select_related('patient', 'consultation', 'hospitalisation')
                        .order_by('pk'))

        plan = []
        for f in factures:
            services = self._services_de(f, db)
            if len(services) > 1:
                plan.append((f, services))

        if not plan:
            self.stdout.write(self.style.SUCCESS(
                f"[{db}] Rien à faire : aucune facture ne regroupe plusieurs services."))
            return

        # ── Aperçu ───────────────────────────────────────────────
        self.stdout.write(f"\n[{db}] {len(plan)} facture(s) à découper :\n")
        for f, services in plan:
            garde = services[0]
            self.stdout.write(
                f"  FAC-{f.pk:04d} — {f.patient} — {f.montant_total:,.0f} FCFA "
                f"— assurance {f.taux_prise_en_charge}%".replace(',', ' '))
            self.stdout.write(f"      reste sur cette facture : {garde[0]} ({garde[1]})")
            for code, objet in services[1:]:
                self.stdout.write(f"      nouvelle facture        : {code} ({objet})")
        self.stdout.write('')

        if dry:
            self.stdout.write(self.style.WARNING("Simulation (--dry-run) : rien n'a été écrit."))
            return

        if not options['force']:
            reponse = input("Confirmer le découpage ? [oui/non] ").strip().lower()
            if reponse not in ('oui', 'o', 'yes', 'y'):
                self.stdout.write(self.style.WARNING("Annulé."))
                return

        # ── Découpage ────────────────────────────────────────────
        creees = 0
        with transaction.atomic(using=db):
            for f, services in plan:
                garde_code, _ = services[0]

                # 1. Une nouvelle facture pour chaque service supplémentaire.
                for code, objet in services[1:]:
                    nouvelle = Facture(
                        patient_id=f.patient_id,
                        assurance_id=f.assurance_id,
                        taux_prise_en_charge=f.taux_prise_en_charge or Decimal('0'),
                        notes=f"Issue du découpage de FAC-{f.pk:04d}.",
                    )
                    setattr(nouvelle, f'{code}_id', objet.pk)
                    nouvelle._state.db = db
                    nouvelle.save(using=db)
                    creees += 1
                    self.stdout.write(
                        f"  + FAC-{nouvelle.pk:04d} — {code} — "
                        f"{nouvelle.montant_total:,.0f} FCFA".replace(',', ' '))

                # 2. La facture d'origine ne garde que son service principal.
                for code, _ in Facture.SERVICES:
                    if code != garde_code:
                        setattr(f, f'{code}_id', None)
                f.save(using=db)
                self.stdout.write(
                    f"  = FAC-{f.pk:04d} — {garde_code} — "
                    f"{f.montant_total:,.0f} FCFA (paiements conservés)".replace(',', ' '))

        self.stdout.write(self.style.SUCCESS(
            f"\n[{db}] Découpage terminé : {len(plan)} facture(s) réduite(s), "
            f"{creees} facture(s) créée(s)."))
