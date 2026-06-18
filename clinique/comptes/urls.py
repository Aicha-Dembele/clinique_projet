from django.urls import path
from . import views

app_name = 'comptes'

urlpatterns = [
    path('mon-profil/', views.mon_profil, name='mon_profil'),

    path('utilisateurs/', views.utilisateurs_liste, name='utilisateurs_liste'),
    path('utilisateurs/ajouter/', views.utilisateur_ajouter, name='utilisateur_ajouter'),
    path('utilisateurs/<int:pk>/modifier/', views.utilisateur_modifier, name='utilisateur_modifier'),
    path('utilisateurs/<int:pk>/toggle-actif/', views.utilisateur_toggle_actif, name='utilisateur_toggle_actif'),

    path('roles/', views.roles_liste, name='roles_liste'),
    path('roles/<int:pk>/modifier/', views.role_modifier, name='role_modifier'),

    path('permissions/', views.permissions_liste, name='permissions_liste'),
    path('utilisateurs/<int:pk>/reset-password/', views.utilisateur_reset_password, name='utilisateur_reset_password'),
    path('mot-de-passe-oublie/', views.mot_de_passe_oublie, name='mot_de_passe_oublie'),

    path('journal-audit/', views.journal_audit, name='journal_audit'),

    path('notifications/', views.notifications_liste, name='notifications_liste'),
    path('notifications/tout-lire/', views.notifications_tout_lire, name='notifications_tout_lire'),
    path('notifications/<int:pk>/ouvrir/', views.notification_ouvrir, name='notification_ouvrir'),
]