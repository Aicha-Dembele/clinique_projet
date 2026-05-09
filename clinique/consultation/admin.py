from django.contrib import admin
from .models import Rendez_vous, Consultation,DossierMedical, Ordonnance, ExamenMedical, ResultatExamen, Traitement, Hospitalisation

@admin.register(Rendez_vous)
class Rendez_vousAdmin(admin.ModelAdmin):
    list_display = ('patient', 'medecin', 'date', 'statut')
    ordering = ('date',)


class ConsultationInline(admin.TabularInline):
    model = Consultation
    extra = 0
    show_change_link = True

class ExamenInline(admin.TabularInline):
    model = ExamenMedical
    extra = 0

class ResultatExamenInline(admin.TabularInline):
    model = ResultatExamen
    extra = 0

class HospitalisationInline(admin.TabularInline):
    model = Hospitalisation
    extra = 0

class OrdonnanceInline(admin.TabularInline):
    model = Ordonnance
    extra = 0

class TraitementInline(admin.TabularInline):
    model = Traitement
    extra = 0

class DossierMedicalAdmin(admin.ModelAdmin):
    list_display = ('patient','date_creation')

    inlines = [
        ConsultationInline,
        ExamenInline,
        ResultatExamenInline,
        HospitalisationInline,
        OrdonnanceInline,
        TraitementInline,

        
    ]


admin.site.register(DossierMedical, DossierMedicalAdmin )


class ExamenMedicalAdmin(admin.ModelAdmin):
    list_display = ('patient', 'laborantin', 'medecin', 'type_examen', 'statut')
    list_filter = ('statut', 'medecin')
    def patient(self, obj):
        return obj.patient

    def laborantin(self, obj):
        return obj.laborantin
    
    def medecin(self, obj):
        return obj.medecin

    def type_examen(self, obj):
        return obj.type_examen

    def statut(self, obj):
        return obj.statut

admin.site.register(ExamenMedical, ExamenMedicalAdmin)




@admin.register(ResultatExamen)
class ResultatExamenAdmin(admin.ModelAdmin):
    list_display = ('patient', 'examen', 'medecin', 'laborantin', 'date_examen')
    list_filter = ('date_examen', 'medecin', 'laborantin')
    search_fields = ('patient__nom', 'examen__nom')
    ordering = ('-date_examen',)
    readonly_fields = ('date_examen',)

class ConsultationAdmin(admin.ModelAdmin):
    inlines = [TraitementInline, OrdonnanceInline]

    list_display = ('nom_patient', 'nom_medecin', 'motif', 'date_consultation')

    def nom_patient(self, obj):
        return obj.dossier.patient if obj.dossier else "Aucun patient"

    def nom_medecin(self, obj):
        return obj.rendez_vous.medecin if obj.rendez_vous else "Aucun médecin"

    def motif(self, obj):
        return obj.motif

    def date_consultation(self, obj):
        return obj.date

    nom_patient.short_description = "Patient"
    nom_medecin.short_description = "Médecin"
    ordering = ('date',)
admin.site.register(Consultation, ConsultationAdmin)


@admin.register(Traitement)
class TraitementAdmin(admin.ModelAdmin):
    list_display = ('patient', 'medecin','traitement_prescrit')

    def patient(self, obj):
        return obj.consultation.dossier.patient
    
    def medecin(self, obj):
        return obj.consultation.rendez_vous.medecin


    def traitement_prescrit(self, obj):
        return obj.description  
    
@admin.register(Ordonnance)
class OrdonnanceAdmin(admin.ModelAdmin):
    list_display = ('patient', 'medecin', 'ordonnance_prescrit')

    def patient(self, obj):
        return obj.consultation.dossier.patient
    
    def medecin(self, obj):
        return obj.consultation.rendez_vous.medecin

    def ordonnance_prescrit(self, obj):
        return obj.medicaments
    
@admin.register(Hospitalisation)
class HospitalisationAdmin(admin.ModelAdmin):
    list_display = ('patient', 'dossier', 'date_entree', 'date_sortie', 'statut')
    list_filter = ('date_entree', 'date_sortie')
    search_fields = ('patient__nom',)
    ordering = ('date_entree',)





