from django.contrib import admin
from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):

    def nom_complet(self, obj):
        return f"{obj.nom} {obj.prenom}"
    nom_complet.short_description = "Nom complet"

    def a_dossier(self, obj):
        return hasattr(obj, 'dossiermedical')
    a_dossier.boolean = True
    a_dossier.short_description = "Dossier médical"

    list_display = ('nom_complet', 'sexe', 'date_naissance', 'telephone', 'a_dossier')
    search_fields = ('nom', 'prenom', 'telephone')
    list_filter = ('sexe',)
    ordering = ('-date_creation',)

