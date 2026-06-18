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

    path('mouvements/',               views.mouvement_liste,      name='mouvements'),
    path('mouvements/<int:pk>/supprimer/', views.mouvement_supprimer, name='mouvement_supprimer'),
]
