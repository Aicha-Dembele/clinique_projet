from django.db import models
from django.contrib.auth.models import User


class Permission(models.Model):
    code = models.CharField(max_length=100, unique=True)
    libelle = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return self.libelle


class Role(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrateur'),
        ('medecin', 'Medecin'),
        ('laborantin', 'Laborantin'),
        ('infirmier', 'Infirmier'),
        ('receptionniste', 'Receptionniste'),
    ]

    code = models.CharField(max_length=30, unique=True, choices=ROLE_CHOICES)
    libelle = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name='roles')

    class Meta:
        ordering = ['libelle']

    def __str__(self):
        return self.libelle

    def has_permission(self, code):
        return self.permissions.filter(code=code).exists()


class Profil(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profil')
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name='profils')
    telephone = models.CharField(max_length=20, blank=True)
    adresse = models.TextField(blank=True)

    medecin = models.OneToOneField(
        'personnel.Medecin', on_delete=models.SET_NULL, null=True, blank=True, related_name='profil')
    infirmier = models.OneToOneField(
        'personnel.Infirmier', on_delete=models.SET_NULL, null=True, blank=True, related_name='profil')
    laborantin = models.OneToOneField(
        'personnel.Laborantin', on_delete=models.SET_NULL, null=True, blank=True, related_name='profil')
    receptionniste = models.OneToOneField(
        'personnel.Receptionniste', on_delete=models.SET_NULL, null=True, blank=True, related_name='profil')

    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.role.libelle})"

    @property
    def role_code(self):
        return self.role.code if self.role_id else None

    def has_permission(self, code):
        if self.role.code == 'admin':
            return True
        return self.role.has_permission(code)
