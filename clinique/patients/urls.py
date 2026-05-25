from django.urls import path
from . import views

app_name = 'patients'

urlpatterns = [
    path('', views.patient_liste, name='liste'),
    path('ajouter/', views.patient_ajouter, name='ajouter'),
    path('<int:pk>/', views.patient_detail, name='detail'),
    path('<int:pk>/modifier/', views.patient_modifier, name='modifier'),
    path('<int:pk>/supprimer/', views.patient_supprimer, name='supprimer'),
    path('accueil/', views.accueil_patients, name='accueil'),
]
