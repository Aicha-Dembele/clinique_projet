from django.db import models
from patients.models import Patient



class Tarif(models.Model):
    TYPE_CHOICES = [
        ('consultation', 'Consultation'),
        ('examen', 'Examen'),
        ('hospitalisation', 'Hospitalisation'),
    ]

    type_service = models.CharField(max_length=20, choices=TYPE_CHOICES)
    specialite = models.CharField(max_length=100, null=True, blank=True)
    nom = models.CharField(max_length=100)  
    prix = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.nom} - {self.prix} FCFA"

class Facture(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    consultation = models.ForeignKey("consultation.Consultation", on_delete=models.SET_NULL, null=True, blank=True)
    examen = models.ForeignKey("consultation.ExamenMedical", on_delete=models.SET_NULL, null=True, blank=True)
    hospitalisation = models.ForeignKey("consultation.Hospitalisation", on_delete=models.SET_NULL, null=True, blank=True)

    montant_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    statut = models.CharField(max_length=20, default='non payé')

    def calculer_total(self):
        total = 0

        # Consultation
        if self.consultation:
            specialite = self.consultation.rendez_vous.medecin.specialite
            tarif = Tarif.objects.filter(
                type_service='consultation',
                specialite=specialite
            ).first()

            if tarif:
                total += tarif.prix
        # Examen
        if self.examen:
            tarif = Tarif.objects.filter(type_service='examen').first()
            if tarif:
                total += tarif.prix
        # Hospitalisation
        if self.hospitalisation:
            tarif = Tarif.objects.filter(type_service='hospitalisation').first()
            if tarif:
                total += tarif.prix
        return total
    def save(self, *args, **kwargs):
        self.montant_total = self.calculer_total()
        super().save(*args, **kwargs)
    def update_statut(self):
        if self.paiements.exists():
            self.statut = 'payé'
        else:
            self.statut = 'non payé'
        self.save()
    def __str__(self):
        return f" {self.patient}  {self.montant_total} FCFA  {self.statut}"    
        

class LigneFacture(models.Model):
    facture = models.ForeignKey(Facture, related_name='lignes', on_delete=models.CASCADE)
    type_service = models.CharField(max_length=50)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    quantite = models.PositiveIntegerField(default=1)

    def sous_total(self):
        return self.prix_unitaire * self.quantite

class Paiement(models.Model):
    MODE_CHOICES = [
        ('cash', 'Espèces'),
        ('orange_money', 'Orange Money'),
        ('moov_money', 'Moov Money'),
        ('carte', 'Carte bancaire'),
    ]

    facture = models.ForeignKey(Facture, related_name='paiements', on_delete=models.CASCADE)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    mode_paiement = models.CharField(max_length=20, choices=MODE_CHOICES)
    date = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Mise à jour automatique du statut
        self.facture.statut='payé'
        self.facture.save()

    def __str__(self):
     return f"{self.montant} FCFA - {self.mode_paiement}"    
        