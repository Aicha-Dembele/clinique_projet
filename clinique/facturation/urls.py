from django.urls import path
from . import views

app_name = 'facturation'

urlpatterns = [
    path('', views.facture_liste, name='liste'),
    path('ajouter/', views.facture_ajouter, name='ajouter'),
    path('<int:pk>/', views.facture_detail, name='detail'),
    path('<int:pk>/supprimer/', views.facture_supprimer, name='supprimer'),
    path('paiements/', views.paiement_liste, name='paiements'),
    path('paiements/ajouter/', views.paiement_ajouter, name='paiement_ajouter'),
    path('rapports/', views.rapports, name='rapports'),
]
