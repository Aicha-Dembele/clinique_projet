from django.contrib import admin
from .models import Medecin, Infirmier, Laborantin, AgentAdministratif, Receptionniste

@admin.register(Medecin)
class MedecinAdmin(admin.ModelAdmin):
    def nom_complet(self, obj):
        return f"{obj.nom} {obj.prenom}"
    nom_complet.short_description = "Nom complet"
    list_display = ('nom_complet', 'specialite')

@admin.register(Infirmier)
class InfirmierAdmin(admin.ModelAdmin):
    def nom_complet(self, obj):
        return f"{obj.nom} {obj.prenom}"
    nom_complet.short_description = "Nom complet"
    list_display = ('nom_complet',  'service')

@admin.register(Laborantin)
class LaborantinAdmin(admin.ModelAdmin):
    def nom_complet(self, obj):
        return f"{obj.nom} {obj.prenom}"
    nom_complet.short_description = "Nom complet"
    list_display = ('nom_complet', 'specialite')

@admin.register(AgentAdministratif)
class AgentAdministratifAdmin(admin.ModelAdmin):
    def nom_complet(self, obj):
        return f"{obj.nom} {obj.prenom}"
    nom_complet.short_description = "Nom complet"
    list_display = ('nom_complet', 'service')


@admin.register(Receptionniste)
class Receptionniste(admin.ModelAdmin):
    def nom_complet(self, obj):
        return f"{obj.nom} {obj.prenom}"
    nom_complet.short_description = "Nom complet"
    list_display = ('nom_complet', 'service')

