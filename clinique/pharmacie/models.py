from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Specialite(models.Model):
    """Spécialité médicale servant à cibler les médicaments à la prescription."""

    code = models.CharField(max_length=40, unique=True)
    nom  = models.CharField(max_length=80)

    class Meta:
        ordering = ['nom']
        verbose_name = "Spécialité"
        verbose_name_plural = "Spécialités"

    def __str__(self):
        return self.nom


class Medicament(models.Model):
    """Médicament géré en stock par la pharmacie de la clinique."""

    CATEGORIE_CHOICES = [
        ('antibiotique',     'Antibiotique'),
        ('antalgique',       'Antalgique / Antidouleur'),
        ('anti_inflammatoire', 'Anti-inflammatoire'),
        ('antipaludique',    'Antipaludique'),
        ('antipyretique',    'Antipyrétique'),
        ('cardiovasculaire', 'Cardiovasculaire'),
        ('digestif',         'Digestif / Gastro'),
        ('respiratoire',     'Respiratoire'),
        ('dermatologique',   'Dermatologique'),
        ('vitamine',         'Vitamines / Compléments'),
        ('solute',           'Soluté / Perfusion'),
        ('antiseptique',     'Antiseptique / Désinfectant'),
        ('consommable',      'Consommable / Matériel médical'),
        ('autre',            'Autre'),
    ]

    nom            = models.CharField(max_length=150)
    dci            = models.CharField(
        max_length=150, blank=True, default='',
        help_text="Dénomination commune internationale (principe actif), ex : Paracétamol.")
    forme          = models.CharField(
        max_length=100, blank=True, default='',
        help_text="Comprimé, sirop, injectable, pommade, gélule…")
    dosage         = models.CharField(
        max_length=60, blank=True, default='',
        help_text="Ex : 500 mg, 1 g, 100 mg/5 ml.")
    categorie      = models.CharField(
        max_length=30, choices=CATEGORIE_CHOICES, blank=True, default='')
    indication     = models.TextField(
        blank=True, default='',
        help_text="À quoi sert ce médicament et dans quels cas le prescrire (aide à la prescription).")
    commun         = models.BooleanField(
        default=False,
        help_text="Médicament de base, proposé à toutes les spécialités.")
    specialites    = models.ManyToManyField(
        Specialite, blank=True, related_name='medicaments',
        help_text="Spécialités pour lesquelles ce médicament est proposé en priorité.")
    unite          = models.CharField(
        max_length=30, default='boîte',
        help_text="Unité de gestion du stock : boîte, comprimé, flacon…")
    prix_unitaire  = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantite_stock = models.PositiveIntegerField(default=0)
    seuil_alerte   = models.PositiveIntegerField(
        default=10,
        help_text="Stock minimal : en dessous (ou égal), une alerte de réapprovisionnement s'affiche.")
    date_peremption = models.DateField(null=True, blank=True)
    actif          = models.BooleanField(default=True)
    date_creation  = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "Médicament"
        verbose_name_plural = "Médicaments"
        ordering = ['nom']

    def __str__(self):
        base = self.nom
        if self.dosage:
            base += f" {self.dosage}"
        return f"{base} — {self.quantite_stock} {self.unite}"

    # ── Libellé complet (nom + dosage + forme) ────────────────────
    def libelle(self):
        parts = [self.nom]
        if self.dosage:
            parts.append(self.dosage)
        if self.forme:
            parts.append(f"({self.forme})")
        return ' '.join(parts)

    # ── État du stock ─────────────────────────────────────────────
    def est_rupture(self):
        """Stock épuisé."""
        return self.quantite_stock <= 0

    def est_en_alerte(self):
        """Stock faible : encore disponible mais sous le seuil."""
        return 0 < self.quantite_stock <= self.seuil_alerte

    def statut_stock(self):
        """'rupture' | 'alerte' | 'ok' — pratique pour le template."""
        if self.est_rupture():
            return 'rupture'
        if self.est_en_alerte():
            return 'alerte'
        return 'ok'

    def valeur_stock(self):
        """Valeur monétaire du stock détenu (prix unitaire × quantité)."""
        return (self.prix_unitaire or Decimal('0')) * self.quantite_stock

    # ── Péremption ────────────────────────────────────────────────
    def est_perime(self):
        return bool(self.date_peremption) and self.date_peremption < timezone.localdate()

    def bientot_perime(self, jours=30):
        if not self.date_peremption or self.est_perime():
            return False
        return self.date_peremption <= timezone.localdate() + timedelta(days=jours)


class MouvementStock(models.Model):
    """Trace chaque entrée (réapprovisionnement) ou sortie (dispensation) de stock.

    Le stock du médicament est ajusté automatiquement à la création du mouvement
    et ré-ajusté en cas de suppression : le `Medicament.quantite_stock` reste donc
    toujours cohérent avec la somme des mouvements.
    """

    TYPE_CHOICES = [
        ('entree', 'Entrée (réapprovisionnement)'),
        ('sortie', 'Sortie (dispensation)'),
    ]

    medicament     = models.ForeignKey(
        Medicament, on_delete=models.CASCADE, related_name='mouvements')
    type_mouvement = models.CharField(max_length=10, choices=TYPE_CHOICES)
    quantite       = models.PositiveIntegerField()
    prix_unitaire  = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Prix unitaire figé au moment du mouvement. Par défaut, celui du médicament.")
    motif          = models.CharField(max_length=200, blank=True, default='')

    # Liens optionnels : une sortie peut correspondre à une ordonnance / un patient
    ordonnance     = models.ForeignKey(
        'consultation.Ordonnance', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dispensations')
    patient        = models.ForeignKey(
        'patients.Patient', on_delete=models.SET_NULL, null=True, blank=True)
    facture        = models.ForeignKey(
        'facturation.Facture', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='mouvements',
        help_text="Facture sur laquelle ce médicament dispensé est porté (le cas échéant).")
    utilisateur    = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    date           = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ['-date']

    def __str__(self):
        signe = '+' if self.type_mouvement == 'entree' else '-'
        return f"{self.get_type_mouvement_display()} {signe}{self.quantite} — {self.medicament.nom}"

    # ── Montant du mouvement (prix figé × quantité) ───────────────
    def montant(self):
        """Valeur monétaire du mouvement : prix unitaire (snapshot) × quantité."""
        return (self.prix_unitaire or Decimal('0')) * self.quantite

    # ── Ajustement automatique du stock ───────────────────────────
    def _appliquer(self, delta):
        """Applique un delta au stock du médicament de façon atomique (F-expression)."""
        Medicament.objects.filter(pk=self.medicament_id).update(
            quantite_stock=models.F('quantite_stock') + delta
        )

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        # Fige le prix courant du médicament si aucun prix n'a été fourni
        if is_new and not self.prix_unitaire:
            self.prix_unitaire = self.medicament.prix_unitaire or Decimal('0')
        super().save(*args, **kwargs)
        if is_new:
            delta = self.quantite if self.type_mouvement == 'entree' else -self.quantite
            self._appliquer(delta)

    def delete(self, *args, **kwargs):
        # Annule l'effet du mouvement avant suppression
        delta = -self.quantite if self.type_mouvement == 'entree' else self.quantite
        self._appliquer(delta)
        facture = self.facture
        super().delete(*args, **kwargs)
        # Recalcule la facture pour retirer la ligne du médicament dispensé
        if facture is not None:
            facture.save()
