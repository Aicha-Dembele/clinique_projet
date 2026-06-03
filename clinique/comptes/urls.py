from django.urls import path
from . import views

app_name = 'comptes'

urlpatterns = [
    path('mon-profil/', views.mon_profil, name='mon_profil'),

    path('utilisateurs/', views.utilisateurs_liste, name='utilisateurs_liste'),
    path('utilisateurs/ajouter/', views.utilisateur_ajouter, name='utilisateur_ajouter'),
    path('utilisateurs/<int:pk>/modifier/', views.utilisateur_modifier, name='utilisateur_modifier'),
    path('utilisateurs/<int:pk>/supprimer/', views.utilisateur_supprimer, name='utilisateur_supprimer'),

    path('roles/', views.roles_liste, name='roles_liste'),
    path('roles/<int:pk>/modifier/', views.role_modifier, name='role_modifier'),

    path('permissions/', views.permissions_liste, name='permissions_liste'),
]
