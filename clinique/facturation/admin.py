from django.contrib import admin
from .models import Facture, Paiement, Tarif, LigneFacture, Assurance


@admin.register(Assurance)
class AssuranceAdmin(admin.ModelAdmin):
    list_display = ('nom', 'taux_prise_en_charge', 'actif')
    list_filter = ('actif',)
    search_fields = ('nom',)


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ('patient', 'type_service', 'montant_total', 'assurance', 'part_patient', 'statut')

    def patient(self, obj):
        return obj.patient
    def part_patient(self, obj):
        return f"{obj.part_patient():,.0f} FCFA"
    part_patient.short_description = "Reste patient"
    def type_service(self, obj):
        services = []
        if obj.consultation:
            services.append("Consultation")
        # Les examens sont désormais des lignes liées à la consultation
        if obj.lignes.filter(type_service='examen').exists():
            services.append("Examen")
        if obj.hospitalisation:
            services.append("Hospitalisation")
        return " + ".join(services) or "—"


class PaiementAdmin(admin.ModelAdmin):
    list_display = ('patient', 'montant', 'mode_paiement', 'date')

    def patient(self, obj):
        return obj.facture.patient
    def mode_paiement(self, obj):
        return obj.mode_paiement
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