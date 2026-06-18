from django.db import models

class Patient(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    sexe = models.CharField(max_length=50)
    date_naissance = models.DateField()
    adresse = models.CharField(max_length=255)
    telephone = models.CharField(max_length=20)
    email = models.EmailField()
    numero_urgence = models.CharField(max_length=20)
    photo = models.ImageField(upload_to='patients/photos/', null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    # Assurance maladie du patient (ex : AMO). Appliquée automatiquement
    # à ses factures, où le taux/l'assurance restent modifiables.
    assurance = models.ForeignKey(
        'facturation.Assurance', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='patients'
    )
    numero_assure = models.CharField(
        max_length=50, blank=True, default='',
        help_text="Numéro d'assuré / matricule (ex : numéro AMO)."
    )

    def __str__(self):
        return f"{self.nom} {self.prenom}"
    


