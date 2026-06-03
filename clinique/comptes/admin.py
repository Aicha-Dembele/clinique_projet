from django.contrib import admin
from .models import Role, Permission, Profil


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle')
    search_fields = ('code', 'libelle')


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('code', 'libelle')
    filter_horizontal = ('permissions',)


@admin.register(Profil)
class ProfilAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'telephone')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
