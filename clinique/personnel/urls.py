from django.urls import path
from . import views

app_name = 'personnel'

urlpatterns = [
    path('', views.personnel_liste, name='liste'),
    path('medecin/ajouter/', views.medecin_ajouter, name='medecin_ajouter'),
    path('medecin/<int:pk>/modifier/', views.medecin_modifier, name='medecin_modifier'),
    path('medecin/<int:pk>/supprimer/', views.medecin_supprimer, name='medecin_supprimer'),
    path('infirmier/ajouter/', views.infirmier_ajouter, name='infirmier_ajouter'),
    path('laborantin/ajouter/', views.laborantin_ajouter, name='laborantin_ajouter'),
    path('receptionniste/ajouter/', views.receptionniste_ajouter, name='receptionniste_ajouter'),
]
