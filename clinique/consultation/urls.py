from django.urls import path
from . import views

app_name = 'consultation'

urlpatterns = [
    # Rendez-vous
    path('rdv/', views.rdv_liste, name='rdv_liste'),
    path('rdv/ajouter/', views.rdv_ajouter, name='rdv_ajouter'),
    path('rdv/<int:pk>/modifier/', views.rdv_modifier, name='rdv_modifier'),
    path('rdv/<int:pk>/supprimer/', views.rdv_supprimer, name='rdv_supprimer'),

    # Dossiers médicaux
    path('dossiers/', views.dossiers, name='dossiers'),
    path('dossiers/<int:pk>/', views.dossier_detail, name='dossier_detail'),
    path('dossiers/<int:pk>/pdf/', views.dossier_pdf, name='dossier_pdf'),

    # Consultations
    path('', views.consultation_liste, name='liste'),
    path('ajouter/', views.consultation_ajouter, name='ajouter'),
    path('<int:pk>/', views.consultation_detail, name='detail'),
    path('<int:pk>/modifier/', views.consultation_modifier, name='modifier'),
    path('<int:pk>/supprimer/', views.consultation_supprimer, name='supprimer'),

    # Examens
    path('examens/', views.examens, name='examens'),
    path('examens/ajouter/', views.examen_ajouter, name='examen_ajouter'),
    path('examens/<int:pk>/modifier/', views.examen_modifier, name='examen_modifier'),
    path('examens/<int:pk>/supprimer/', views.examen_supprimer, name='examen_supprimer'),

    # Resultats
    path('resultats/', views.resultats, name='resultats'),
    path('resultats/ajouter/', views.resultat_ajouter, name='resultat_ajouter'),
    path('resultats/corbeille/', views.resultat_corbeille, name='resultat_corbeille'),
    path('resultats/<int:pk>/', views.resultat_detail, name='resultat_detail'),
    path('resultats/<int:pk>/pdf/', views.resultat_pdf, name='resultat_pdf'),
    path('resultats/<int:pk>/modifier/', views.resultat_modifier, name='resultat_modifier'),
    path('resultats/<int:pk>/transmettre/', views.resultat_transmettre, name='resultat_transmettre'),
    path('resultats/<int:pk>/supprimer/', views.resultat_supprimer, name='resultat_supprimer'),
    path('resultats/<int:pk>/restaurer/', views.resultat_restaurer, name='resultat_restaurer'),
    path('resultats/<int:pk>/purger/', views.resultat_purger, name='resultat_purger'),

    # Ordonnances
    path('ordonnances/', views.ordonnances, name='ordonnances'),
    path('ordonnances/ajouter/', views.ordonnance_ajouter, name='ordonnance_ajouter'),
    path('ordonnances/<int:pk>/', views.ordonnance_detail, name='ordonnance_detail'),
    path('ordonnances/<int:pk>/imprimer/', views.ordonnance_imprimer, name='ordonnance_imprimer'),
    path('ordonnances/<int:pk>/supprimer/', views.ordonnance_supprimer, name='ordonnance_supprimer'),

    # Hospitalisations
    path('hospitalisations/', views.hospitalisations, name='hospitalisations'),
    path('hospitalisations/ajouter/', views.hospit_ajouter, name='hospit_ajouter'),
    path('hospitalisations/<int:pk>/modifier/', views.hospit_modifier, name='hospit_modifier'),
    path('hospitalisations/<int:pk>/sortie/', views.hospit_sortie, name='hospit_sortie'),
    path('hospitalisations/<int:pk>/supprimer/', views.hospit_supprimer, name='hospit_supprimer'),

    # Traitements
    path('traitements/', views.traitements, name='traitements'),
    path('traitements/ajouter/', views.traitement_ajouter, name='traitement_ajouter'),
    path('traitements/<int:pk>/', views.traitement_detail, name='traitement_detail'),
    path('traitements/<int:pk>/suivi.json', views.traitement_suivi, name='traitement_suivi'),
    path('traitements/<int:pk>/administrer/', views.traitement_administrer, name='traitement_administrer'),
    path('traitements/<int:pk>/statut/', views.traitement_statut, name='traitement_statut'),
    path('traitements/<int:pk>/supprimer/', views.traitement_supprimer, name='traitement_supprimer'),

    # Assistances infirmier
    path('assistances/', views.assistances, name='assistances'),
    path('assistances/ajouter/', views.assistance_ajouter, name='assistance_ajouter'),
]
