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
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom} {self.prenom}"
    


