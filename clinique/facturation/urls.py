from django.urls import path
from . import views

app_name = 'facturation'

urlpatterns = [
    path('', views.facture_liste, name='liste'),
    path('ajouter/', views.facture_ajouter, name='ajouter'),
    path('<int:pk>/', views.facture_detail, name='detail'),
    path('<int:pk>/modifier/', views.facture_modifier, name='modifier'),
    path('<int:pk>/supprimer/', views.facture_supprimer, name='supprimer'),
    path('paiements/', views.paiement_liste, name='paiements'),
    path('paiements/ajouter/', views.paiement_ajouter, name='paiement_ajouter'),
    path('paiements/<int:pk>/modifier/', views.paiement_modifier, name='paiement_modifier'),
    path('paiements/<int:pk>/supprimer/', views.paiement_supprimer, name='paiement_supprimer'),
    path('paiements/<int:pk>/recu/', views.paiement_recu, name='paiement_recu'),
    path('rapports/', views.rapports, name='rapports'),
    path('tarifs/', views.tarif_liste, name='tarifs'),
    path('tarifs/ajouter/', views.tarif_ajouter, name='tarif_ajouter'),
    path('tarifs/<int:pk>/modifier/', views.tarif_modifier, name='tarif_modifier'),
    path('tarifs/<int:pk>/supprimer/', views.tarif_supprimer, name='tarif_supprimer'),
]
