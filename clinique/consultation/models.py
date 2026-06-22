from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from personnel.models import Laborantin, Medecin
from patients.models import Patient
from facturation.models import Tarif


class NonSupprimeManager(models.Manager):
    """Manager par défaut qui exclut les enregistrements en corbeille
    (supprime=True). La corbeille reste accessible via `objets_tous`."""

    def get_queryset(self):
        return super().get_queryset().filter(supprime=False)



def get_or_create_dossier(patient):
    from .models import DossierMedical
    dossier, created = DossierMedical.objects.get_or_create(patient=patient)
    return dossier

class Rendez_vous(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    medecin = models.ForeignKey("personnel.Medecin", on_delete=models.CASCADE)
    date = models.DateTimeField()

    STATUT_CHOICES = [
        ('programme', 'Programmé'),
        ('termine', 'Terminé'),
        ('annule', 'Annulé'),
    ]

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='programme'
    )

    def __str__(self):
        return f"{self.patient} - {self.medecin} - {self.date}"

    class Meta:
        unique_together = ('medecin', 'date')

class DossierMedical(models.Model):
    patient = models.OneToOneField(Patient, on_delete=models.CASCADE)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Dossier de {self.patient}"

class Consultation(models.Model):
    rendez_vous = models.OneToOneField(Rendez_vous, on_delete=models.CASCADE,
        related_name="consultation")
    dossier = models.ForeignKey(DossierMedical, on_delete=models.CASCADE,
        related_name="consultations", null=True, blank=True)
    motif = models.TextField()
    diagnostic = models.TextField()
    observation = models.TextField(blank=True, default='')
    date = models.DateTimeField(auto_now_add=True)

    def get_tarif(self):
        try:
            return Tarif.objects.get(
                type_service='consultation',
                specialite=self.rendez_vous.medecin.specialite)
        except Tarif.DoesNotExist:
            return Tarif.objects.filter(type_service='consultation').first()

    def save(self, *args, **kwargs):
        if not self.dossier_id:
            patient = self.rendez_vous.patient
            self.dossier, _ = DossierMedical.objects.get_or_create(patient=patient)
        super().save(*args, **kwargs)
        if self.rendez_vous and self.rendez_vous.statut != 'termine':
            self.rendez_vous.statut = 'termine'
            self.rendez_vous.save()

    def __str__(self):
        return f"Consultation de {self.rendez_vous.patient}"


class ExamenMedical(models.Model):
    
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    dossier= models.ForeignKey(DossierMedical, on_delete=models.CASCADE,
        related_name="examens", null=True, blank=True)
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE)
    laborantin = models.ForeignKey("personnel.Laborantin", on_delete=models.CASCADE, null=True, blank=True)
    medecin = models.ForeignKey("personnel.Medecin", on_delete=models.CASCADE, null=True, blank=True)
    type_examen = models.CharField(max_length=100)
    motif = models.CharField(max_length=255, blank=True, default='')
    date = models.DateField(null=True, blank=True)
    STATUT_CHOICES = [
    ('en_attente', 'En attente'),
    ('en_cours', 'En cours'),
    ('termine', 'Terminé'),
]

    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_cours')

   
    def get_tarif(self):
        try:
            return Tarif.objects.get(
                type_service='examen',
                specialite=self.type_examen
            )
        except Tarif.DoesNotExist:
            return Tarif.objects.filter(type_service='examen').first()

    def save(self, *args, **kwargs):
        if not self.dossier_id:
            dossier, _ = DossierMedical.objects.get_or_create(patient=self.patient)
            self.dossier = dossier
        super().save(*args, **kwargs)

    def __str__(self):
        return self.type_examen 
    

class ResultatExamen(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    dossier = models.ForeignKey(DossierMedical, on_delete=models.CASCADE, related_name='resultats', null=True, blank=True)
    examen = models.ForeignKey(ExamenMedical, on_delete=models.CASCADE, related_name='resultats')
    medecin = models.ForeignKey("personnel.Medecin", on_delete=models.SET_NULL, null=True, blank=True)
    laborantin = models.ForeignKey("personnel.Laborantin", on_delete=models.SET_NULL, null=True, blank=True)
    resultat = models.TextField()
    observations = models.TextField(blank=True, default='')
    transmis = models.BooleanField(default=False)
    date_transmission = models.DateTimeField(null=True, blank=True)
    date_examen = models.DateTimeField(auto_now_add=True)

    # ── Corbeille (soft-delete) ──
    supprime = models.BooleanField(default=False)
    date_suppression = models.DateTimeField(null=True, blank=True)
    supprime_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    objects = NonSupprimeManager()   # défaut : exclut la corbeille
    objets_tous = models.Manager()   # accès complet, corbeille incluse

    class Meta:
        # _base_manager (cascades, relations) doit voir TOUS les enregistrements.
        base_manager_name = 'objets_tous'

    def save(self, *args, **kwargs):
        if not self.dossier_id:
            dossier, _ = DossierMedical.objects.get_or_create(patient=self.patient)
            self.dossier = dossier
        if self.examen and self.examen.statut != 'termine':
            self.examen.statut = 'termine'
            self.examen.save()
        super().save(*args, **kwargs)

    def soft_delete(self, user=None):
        """Déplace le résultat vers la corbeille au lieu de l'effacer."""
        self.supprime = True
        self.date_suppression = timezone.now()
        self.supprime_par = user if getattr(user, 'is_authenticated', False) else None
        self.save(update_fields=['supprime', 'date_suppression', 'supprime_par'])

    def restaurer(self):
        """Restaure un résultat depuis la corbeille."""
        self.supprime = False
        self.date_suppression = None
        self.supprime_par = None
        self.save(update_fields=['supprime', 'date_suppression', 'supprime_par'])

    def __str__(self):
        return f"{self.patient} - {self.examen}"

    
      
    
class Traitement(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, null=True, blank=True)
    dossier = models.ForeignKey(DossierMedical, related_name="traitement", on_delete=models.CASCADE, null=True, blank=True)
    infirmier = models.ForeignKey("personnel.Infirmier", on_delete=models.SET_NULL, null=True, blank=True, related_name='traitements_assignes')

    description = models.TextField()
    duree = models.IntegerField(help_text="Duree en jours")
    statut = models.CharField(max_length=20, choices=[
        ('prescrit', 'Prescrit'),
        ('en_cours', 'En cours'),
        ('termine', 'Termine'),
    ], default='prescrit')
    date_creation = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        if not self.dossier and self.consultation:
            self.dossier = self.consultation.dossier
        if not self.dossier and self.patient:
            self.dossier, _ = DossierMedical.objects.get_or_create(patient=self.patient)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Traitement de {self.patient}"


class AdministrationTraitement(models.Model):
    traitement = models.ForeignKey(Traitement, on_delete=models.CASCADE, related_name='administrations')
    infirmier = models.ForeignKey("personnel.Infirmier", on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, default='')

    def __str__(self):
        return f"Admin {self.traitement} - {self.date:%Y-%m-%d %H:%M}"


class AssistanceInfirmier(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='assistances')
    dossier = models.ForeignKey(DossierMedical, on_delete=models.CASCADE, related_name='assistances', null=True, blank=True)
    infirmier = models.ForeignKey("personnel.Infirmier", on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField()
    date = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.dossier_id and self.patient_id:
            self.dossier, _ = DossierMedical.objects.get_or_create(patient=self.patient)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Assistance {self.patient} - {self.date:%Y-%m-%d}"
    
class Ordonnance(models.Model):
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE)
    dossier = models.ForeignKey(DossierMedical, related_name="ordonnance", on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    medicaments = models.TextField()

    def save(self, *args, **kwargs):
        if not self.dossier:
            self.dossier = self.consultation.dossier
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ordonnance {self.consultation}"
        

class Hospitalisation(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    medecin = models.ForeignKey("personnel.Medecin", on_delete=models.CASCADE)
    dossier = models.ForeignKey(DossierMedical, on_delete=models.CASCADE,
        related_name="hospitalisations", null=True, blank=True)
    type_chambre = models.CharField(max_length=100, default="standard")
    nombre_jours = models.IntegerField(default=1)
    numero_chambre = models.CharField(max_length=10)
    date_entree = models.DateField()
    date_sortie = models.DateField(null=True, blank=True)

    ETAT_CHOICES = [('stable', 'Stable'), ('critique', 'Critique')]
    etat_clinique = models.CharField(max_length=20, choices=ETAT_CHOICES, default='stable')

    # Nombre maximum de patients qu'une chambre peut accueillir selon son type.
    CAPACITE_CHAMBRE = {'simple': 6, 'double': 2, 'vip': 1}

    @classmethod
    def plan_chambres(cls):
        """Inventaire fixe de l'établissement : 40 chambres typées (numéro, type).

        - 10 VIP    : 101-110            (1 patient)
        - 12 doubles : 201-210, 301-302  (2 patients)
        - 18 simples : 303-310, 401-410  (6 patients)
        """
        vip = [str(100 + i) for i in range(1, 11)]
        double = [str(200 + i) for i in range(1, 11)] + ['301', '302']
        simple = [str(300 + i) for i in range(3, 11)] + [str(400 + i) for i in range(1, 11)]
        return ([(n, 'vip') for n in vip]
                + [(n, 'double') for n in double]
                + [(n, 'simple') for n in simple])

    @classmethod
    def type_pour_numero(cls, numero):
        """Type de chambre associé à un numéro selon le plan, ou None si inconnu."""
        numero = (numero or '').strip()
        return dict(cls.plan_chambres()).get(numero)

    @classmethod
    def capacite_pour(cls, type_chambre):
        """Capacité (nb de patients) d'une chambre de ce type. 1 par défaut."""
        return cls.CAPACITE_CHAMBRE.get((type_chambre or '').strip().lower(), 1)

    @classmethod
    def occupants_actifs(cls, numero_chambre, exclure_pk=None):
        """Nombre de patients actuellement hospitalisés (non sortis) dans cette chambre."""
        qs = cls.objects.filter(
            numero_chambre__iexact=(numero_chambre or '').strip(),
            date_sortie__isnull=True,
        )
        if exclure_pk:
            qs = qs.exclude(pk=exclure_pk)
        return qs.count()

    def get_prix_nuit(self):
        """Retourne le prix par nuit selon le type de chambre."""
        tarif = (
            Tarif.objects.filter(
                type_service='hospitalisation',
                specialite__iexact=self.type_chambre
            ).first()
            or Tarif.objects.filter(type_service='hospitalisation').first()
        )
        return tarif.prix if tarif else 0

    def get_tarif(self):
        """Retourne le total = prix_nuit x nombre_jours."""
        return self.get_prix_nuit() * self.nombre_jours

    def save(self, *args, **kwargs):
        if not self.dossier_id:
            dossier, _ = DossierMedical.objects.get_or_create(patient=self.patient)
            self.dossier = dossier
        super().save(*args, **kwargs)

    def statut(self):
        return "En cours" if not self.date_sortie else "Sorti"

    statut.short_description = "Statut"

    def date_sortie_prevue(self):
        """Date de sortie : reelle si renseignee, sinon estimee (entree + nombre de jours)."""
        from datetime import timedelta
        if self.date_sortie:
            return self.date_sortie
        if self.date_entree:
            return self.date_entree + timedelta(days=self.nombre_jours or 0)
        return None

    def etat(self):
        """Etat clinique affiche dans la liste (Stable / Critique / Sorti / Sortie auj.).

        Pour un patient hospitalise, l'etat est choisi a l'admission (champ
        etat_clinique) ; la sortie a la priorite sur tout le reste.
        """
        from datetime import date
        if self.date_sortie:
            if self.date_sortie == date.today():
                return {'code': 'sortie', 'label': 'Sortie auj.'}
            return {'code': 'sorti', 'label': 'Sorti'}
        if (self.etat_clinique or '').lower() == 'critique':
            return {'code': 'critique', 'label': 'Critique'}
        return {'code': 'stable', 'label': 'Stable'}

    def __str__(self):
        return f"Hospitalisation {self.patient}"