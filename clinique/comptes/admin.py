from django.contrib import admin
from .models import Role, Permission, Profil, JournalAudit


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


@admin.register(JournalAudit)
class JournalAuditAdmin(admin.ModelAdmin):
    list_display = ('date', 'user', 'action', 'modele', 'objet_id', 'objet_repr')
    list_filter = ('action', 'modele', 'date')
    search_fields = ('objet_repr', 'objet_id', 'details', 'user__username')
    date_hierarchy = 'date'
    # Le journal d'audit est en lecture seule (intégrité de la traçabilité).
    readonly_fields = ('user', 'action', 'modele', 'objet_id', 'objet_repr', 'details', 'date')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
