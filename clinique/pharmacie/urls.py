from django.urls import path
from . import views

app_name = 'pharmacie'

urlpatterns = [
    path('',                          views.medicament_liste,     name='medicaments'),
    path('ajouter/',                  views.medicament_ajouter,   name='medicament_ajouter'),
    path('<int:pk>/modifier/',        views.medicament_modifier,  name='medicament_modifier'),
    path('<int:pk>/supprimer/',       views.medicament_supprimer, name='medicament_supprimer'),

    path('entree/',                   views.entree_stock,         name='entree_stock'),
    path('sortie/',                   views.sortie_stock,         name='sortie_stock'),

    path('remboursement/',            views.remboursement_liste,  name='remboursement'),

    # Approvisionnement : d'ou vient la marchandise.
    path('fournisseurs/',             views.fournisseur_liste,    name='fournisseurs'),
    path('fournisseurs/ajouter/',     views.fournisseur_form,     name='fournisseur_ajouter'),
    path('fournisseurs/<int:pk>/modifier/', views.fournisseur_form, name='fournisseur_modifier'),

    path('commandes/',                views.commande_liste,       name='commandes'),
    path('commandes/nouvelle/',       views.commande_ajouter,     name='commande_ajouter'),
    path('commandes/<int:pk>/',       views.commande_detail,      name='commande_detail'),
    path('commandes/<int:pk>/reception/', views.commande_receptionner, name='commande_receptionner'),

    path('mouvements/',               views.mouvement_liste,      name='mouvements'),
    path('mouvements/<int:pk>/supprimer/', views.mouvement_supprimer, name='mouvement_supprimer'),
]
