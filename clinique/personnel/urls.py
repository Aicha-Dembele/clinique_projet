from django.urls import path
from . import views

app_name = 'personnel'

urlpatterns = [
    path('', views.personnel_liste, name='liste'),
    path('medecin/ajouter/', views.medecin_ajouter, name='medecin_ajouter'),
    path('medecin/<int:pk>/modifier/', views.medecin_modifier, name='medecin_modifier'),
    path('medecin/<int:pk>/supprimer/', views.medecin_supprimer, name='medecin_supprimer'),
    path('infirmier/ajouter/', views.infirmier_ajouter, name='infirmier_ajouter'),
    path('infirmier/<int:pk>/modifier/', views.infirmier_modifier, name='infirmier_modifier'),
    path('infirmier/<int:pk>/supprimer/', views.infirmier_supprimer, name='infirmier_supprimer'),
    path('laborantin/ajouter/', views.laborantin_ajouter, name='laborantin_ajouter'),
    path('laborantin/<int:pk>/modifier/', views.laborantin_modifier, name='laborantin_modifier'),
    path('laborantin/<int:pk>/supprimer/', views.laborantin_supprimer, name='laborantin_supprimer'),
    path('receptionniste/ajouter/', views.receptionniste_ajouter, name='receptionniste_ajouter'),
    path('receptionniste/<int:pk>/modifier/', views.receptionniste_modifier, name='receptionniste_modifier'),
    path('receptionniste/<int:pk>/supprimer/', views.receptionniste_supprimer, name='receptionniste_supprimer'),
]
