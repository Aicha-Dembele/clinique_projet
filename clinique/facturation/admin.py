from django.contrib import admin
from .models import Facture, Paiement, Tarif, LigneFacture


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ('patient', 'type_service', 'montant_total', 'statut')

    def patient(self, obj):
        return obj.patient
    def type_service(self, obj):
        services = []
        if obj.consultation:
            services.append("Consultation")
        if obj.examen:
            services.append("Examen")
        if obj.hospitalisation:
            services.append("Hospitalisation")
        return " + ".join(services)


class PaiementAdmin(admin.ModelAdmin):
    list_display = ('patient', 'montant', 'mode_paiement', 'date')

    def patient(self, obj):
        return obj.facture.patient
    def mode_paiement(self, obj):
        return obj.facture.mode_paiement
    def date(self, obj):
        return obj.date
    patient.short_description = "Patient"
    mode_paiement.short_description = "Mode_paiement"
    date.short_description = "Date"
admin.site.register(Paiement, PaiementAdmin)


@admin.register(Tarif)
class TarifAdmin(admin.ModelAdmin):
   def prix_affiche(self, obj):
        return f"{obj.prix} FCFA"
   prix_affiche.short_description = "Prix"

   list_display = ('nom', 'type_service', 'specialite', 'prix_affiche')
   list_filter = ('type_service', 'specialite')
   search_fields = ('nom', 'specialite')
   ordering = ('type_service', 'prix')




admin.site.register(LigneFacture)