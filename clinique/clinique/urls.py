from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView
from dashboard_view import dashboard

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='login', permanent=False)),
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('dashboard/', dashboard, name='dashboard'),
    path('patients/', include('patients.urls')),
    path('personnel/', include('personnel.urls')),
    path('consultation/', include('consultation.urls')),
    path('facturation/', include('facturation.urls')),
    path('comptes/', include('comptes.urls')),
]