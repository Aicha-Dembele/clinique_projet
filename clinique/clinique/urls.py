from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from dashboard_view import dashboard
from comptes.views import ConnexionView

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='login', permanent=False)),
    path('admin/', admin.site.urls),
    path('login/', ConnexionView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    # Réinitialisation du mot de passe oublié (par email)
    path('password-reset/', auth_views.PasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    path('dashboard/', dashboard, name='dashboard'),
    path('patients/', include('patients.urls')),
    path('personnel/', include('personnel.urls')),
    path('consultation/', include('consultation.urls')),
    path('facturation/', include('facturation.urls')),
    path('comptes/', include('comptes.urls')),
    path('pharmacie/', include('pharmacie.urls')),
]

# Service des fichiers téléversés (photos, scans) en développement.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)