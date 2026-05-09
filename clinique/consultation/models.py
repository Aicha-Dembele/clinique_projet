from django.db import models
from personnel.models import Laborantin, Medecin
from patients.models import Patient
from facturation.models import Tarif 



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
    date = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        patient = self.rendez_vous.patient

        #  Vérifier si le dossier existe
        dossier, created = DossierMedical.objects.get_or_create(patient=patient)
        # Lier automatiquement
        self.dossier_medical = dossier

        super().save(*args, **kwargs)

        #  Mettre le rendez-vous en terminé
        if self.rendez_vous.statut != 'termine':
            self.rendez_vous.statut = 'termine'
            self.rendez_vous.save()
    def get_tarif(self):
        return Tarif.objects.get(
            type_tarif='consultation',
            specialite=self.medecin.specialite)
    
    def save(self, *args, **kwargs):
        if not self.dossier:
            patient = self.rendez_vous.patient
            self.dossier = get_or_create_dossier(patient)
        super().save(*args, **kwargs)
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        print("SAVE CONSULTATION OK")

        if self.rendez_vous:
           print("RENDEZ-VOUS TROUVÉ")
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
    STATUT_CHOICES = [
    ('en_attente', 'En attente'),
    ('en_cours', 'En cours'),
    ('termine', 'Terminé'),
]

    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='en_attente')

   
    def get_tarif(self):
        return Tarif.objects.get(
            type_tarif='examen',
            specialite=self.type_examen
        )
    def save(self, *args, **kwargs):

    # Vérifier si le patient a déjà un dossier
        dossier, created = DossierMedical.objects.get_or_create(
        patient=self.patient
    )

    # Associer automatiquement
        self.dossier = dossier

        super().save(*args, **kwargs)

    def save(self, *args, **kwargs):
        if not self.dossier:
            self.dossier = get_or_create_dossier(self.patient)
        super().save(*args, **kwargs)    
    def __str__(self):
        return self.type_examen 
    

class ResultatExamen(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    dossier = models.OneToOneField(DossierMedical, on_delete=models.CASCADE, related_name='resultats')
    examen = models.ForeignKey(ExamenMedical, on_delete=models.CASCADE)
    medecin = models.ForeignKey("personnel.Medecin", on_delete=models.SET_NULL, null=True)
    laborantin = models.ForeignKey("personnel.Laborantin", on_delete=models.SET_NULL, null=True)
    resultat = models.TextField()
    date_examen = models.DateTimeField(auto_now_add=True)

    
         #  Vérifier si le dossier existe
    def save(self, *args, **kwargs):
        dossier, created = DossierMedical.objects.get_or_create(patient=self.patient)
        # Lier automatiquement
        self.dossier = dossier
        super().save(*args, **kwargs)
    
    
 
    def __str__(self):
        return f"{self.patient} - {self.examen}" 

    
      
    
class Traitement(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE)
    dossier = models.ForeignKey(DossierMedical, related_name="traitement", on_delete=models.CASCADE, null=True, blank=True)

    description = models.TextField()
    duree = models.IntegerField()

    def save(self, *args, **kwargs):
        if not self.dossier:
            self.dossier = self.consultation.dossier
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Traitement de {self.consultation}"
    
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
    
    def get_tarif(self):
        tarif = Tarif.objects.get(type_tarif='hospitalisation')
        return tarif.prix * self.nombre_jours
    def save(self, *args, **kwargs):

    #Vérifier si le patient a déjà un dossier
      dossier, created = DossierMedical.objects.get_or_create(
        patient=self.patient
    )

    #Associer automatiquement
      self.dossier = dossier

      super().save(*args, **kwargs)
    def save(self, *args, **kwargs):
        if not self.dossier:
            self.dossier = get_or_create_dossier(self.patient)
        super().save(*args, **kwargs) 
    def statut(self):
        return "En cours" if not self.date_sortie else "Sorti"

    statut.short_description = "Statut"     
    def __str__(self):
        return f"Hospitalisation {self.patient}"    
    


