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


class Notification(models.Model):
    """Notification destinée à un utilisateur (cloche dans la barre du haut)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    titre = models.CharField(max_length=200)
    message = models.TextField(blank=True, default='')
    url = models.CharField(max_length=300, blank=True, default='')
    icone = models.CharField(max_length=50, default='bi-bell-fill')
    lu = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.titre} → {self.user.username}"

    @classmethod
    def creer(cls, user, titre, message='', url='', icone='bi-bell-fill'):
        """Crée une notification ; ignore silencieusement si user est None."""
        if not user:
            return None
        return cls.objects.create(
            user=user, titre=titre, message=message, url=url, icone=icone)


class JournalAudit(models.Model):
    """Journal d'audit : trace les actions sensibles (création, modification,
    suppression, restauration) sur les données médicales et financières.
    Essentiel pour la confidentialité et la responsabilité en milieu de santé."""

    ACTION_CHOICES = [
        ('creation', 'Création'),
        ('modification', 'Modification'),
        ('suppression', 'Suppression'),
        ('restauration', 'Restauration'),
        ('purge', 'Suppression définitive'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='actions_audit')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    modele = models.CharField(max_length=100)               # ex. "ResultatExamen"
    objet_id = models.CharField(max_length=50, blank=True, default='')
    objet_repr = models.CharField(max_length=300, blank=True, default='')
    details = models.TextField(blank=True, default='')
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "Entrée d'audit"
        verbose_name_plural = "Journal d'audit"

    def __str__(self):
        return f"{self.get_action_display()} {self.modele} #{self.objet_id}"

    @classmethod
    def enregistrer(cls, user, action, objet, details=''):
        """Enregistre une action dans le journal. `objet` est l'instance
        concernée (on en extrait le nom de modèle, l'id et la représentation)."""
        return cls.objects.create(
            user=user if getattr(user, 'is_authenticated', False) else None,
            action=action,
            modele=objet.__class__.__name__,
            objet_id=str(getattr(objet, 'pk', '') or ''),
            objet_repr=str(objet)[:300],
            details=details,
        )
