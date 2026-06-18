from django.contrib import admin

from .models import Medicament, MouvementStock


@admin.register(Medicament)
class MedicamentAdmin(admin.ModelAdmin):
    list_display = ('nom', 'dosage', 'categorie', 'quantite_stock', 'unite',
                    'seuil_alerte', 'prix_unitaire', 'actif')
    list_filter = ('categorie', 'actif')
    search_fields = ('nom', 'dci')
    ordering = ('nom',)


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ('date', 'type_mouvement', 'medicament', 'quantite',
                    'patient', 'utilisateur')
    list_filter = ('type_mouvement', 'date')
    search_fields = ('medicament__nom', 'motif')
    date_hierarchy = 'date'
    autocomplete_fields = ()
