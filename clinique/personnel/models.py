from django.db import models


class Personnel(models.Model):
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    telephone = models.CharField(max_length=20)
    adresse = models.TextField()
    service = models.CharField(max_length=100)
    role = models.CharField(max_length=50)
    mot_de_passe = models.CharField(max_length=255)
    photo = models.ImageField(upload_to='personnel/photos/', null=True, blank=True)

    class Meta:
        abstract = True

class Medecin(Personnel):
    specialite = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.nom} {self.prenom} {self.specialite}"

class Infirmier(Personnel):
    service = models.CharField(max_length=100)
    def __str__(self):
        return f"{self.nom} {self.prenom}  - {self.service}"

class Laborantin(Personnel):
    specialite = models.CharField(max_length=100)
    def __str__(self):
        return f"{self.nom} {self.prenom} {self.specialite}"

class AgentAdministratif(Personnel):
    service = models.CharField(max_length=100) 
    def __str__(self):
        return f"{self.nom} {self.prenom} {self.service}"  

class Receptionniste(Personnel):
    service = models.CharField(max_length=100)
    def __str__(self):
        return f"{self.nom} {self.prenom} {self.service}"

class Pharmacien(Personnel):
    service = models.CharField(max_length=100)
    def __str__(self):
        return f"{self.nom} {self.prenom} {self.service}"
