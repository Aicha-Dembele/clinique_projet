from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views

from django.core.paginator import Paginator

from .models import Profil, Role, Permission, Notification, JournalAudit
from .decorators import admin_required, role_required
from personnel.models import Medecin, Infirmier, Laborantin, Receptionniste


# Durée de session quand « Se souvenir de moi » est coché (30 jours).
REMEMBER_ME_AGE = 60 * 60 * 24 * 30


class ConnexionView(auth_views.LoginView):
    """Page de connexion gérant la case « Se souvenir de moi »."""
    template_name = 'login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get('remember'):
            # Session conservée 30 jours, même après fermeture du navigateur.
            self.request.session.set_expiry(REMEMBER_ME_AGE)
        else:
            # Session expirée à la fermeture du navigateur.
            self.request.session.set_expiry(0)
        return response


@login_required
def mon_profil(request):
    return render(request, 'comptes/mon_profil.html', {})


@admin_required
def utilisateurs_liste(request):
    profils = Profil.objects.select_related('user', 'role').order_by('user__username')
    q = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '')
    if q:
        profils = profils.filter(user__username__icontains=q) | \
                  profils.filter(user__first_name__icontains=q) | \
                  profils.filter(user__last_name__icontains=q)
    if role_filter:
        profils = profils.filter(role__code=role_filter)
    return render(request, 'comptes/utilisateurs_liste.html', {
        'profils': profils,
        'roles': Role.objects.all(),
        'q': q,
        'role_filter': role_filter,
    })


@admin_required
def utilisateur_ajouter(request):
    roles = Role.objects.all()
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        role_id = request.POST.get('role')
        telephone = request.POST.get('telephone', '').strip()
        adresse = request.POST.get('adresse', '').strip()
        personnel_id = request.POST.get('personnel_id', '').strip()

        if not username or not password or not role_id:
            messages.error(request, "Champs obligatoires manquants.")
            return render(request, 'comptes/utilisateur_form.html', {'roles': roles})
        if User.objects.filter(username=username).exists():
            messages.error(request, "Ce nom d'utilisateur existe deja.")
            return render(request, 'comptes/utilisateur_form.html', {'roles': roles})

        role = get_object_or_404(Role, pk=role_id)
        with transaction.atomic():
            user = User.objects.create_user(
                username=username, password=password,
                first_name=first_name, last_name=last_name, email=email)
            if role.code == 'admin':
                user.is_staff = True
                user.is_superuser = True
                user.save()

            profil = Profil(user=user, role=role, telephone=telephone, adresse=adresse)
            if personnel_id:
                # Détache ce personnel de tout autre profil existant (contrainte UNIQUE)
                if role.code == 'medecin':
                    Profil.objects.filter(medecin_id=personnel_id).update(medecin=None)
                    profil.medecin = Medecin.objects.filter(pk=personnel_id).first()
                elif role.code == 'infirmier':
                    Profil.objects.filter(infirmier_id=personnel_id).update(infirmier=None)
                    profil.infirmier = Infirmier.objects.filter(pk=personnel_id).first()
                elif role.code == 'laborantin':
                    Profil.objects.filter(laborantin_id=personnel_id).update(laborantin=None)
                    profil.laborantin = Laborantin.objects.filter(pk=personnel_id).first()
                elif role.code == 'receptionniste':
                    Profil.objects.filter(receptionniste_id=personnel_id).update(receptionniste=None)
                    profil.receptionniste = Receptionniste.objects.filter(pk=personnel_id).first()
            profil.save()
        messages.success(request, "Utilisateur cree avec succes.")
        return redirect('comptes:utilisateurs_liste')

    return render(request, 'comptes/utilisateur_form.html', {
        'roles': roles,
        'medecins': Medecin.objects.all(),
        'infirmiers': Infirmier.objects.all(),
        'laborantins': Laborantin.objects.all(),
        'receptionnistes': Receptionniste.objects.all(),
    })


@admin_required
def utilisateur_modifier(request, pk):
    profil = get_object_or_404(Profil.objects.select_related('user', 'role'), pk=pk)
    user = profil.user
    roles = Role.objects.all()
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.email = request.POST.get('email', '').strip()
        user.is_active = request.POST.get('is_active') == 'on'
        new_password = request.POST.get('password', '')
        if new_password:
            user.set_password(new_password)

        role_id = request.POST.get('role')
        if role_id:
            role = get_object_or_404(Role, pk=role_id)
            profil.role = role
            user.is_staff = (role.code == 'admin')
            user.is_superuser = (role.code == 'admin')

        profil.telephone = request.POST.get('telephone', '').strip()
        profil.adresse = request.POST.get('adresse', '').strip()

        personnel_id = request.POST.get('personnel_id', '').strip() or None
        profil.medecin = profil.infirmier = profil.laborantin = profil.receptionniste = None

        if personnel_id:
            with transaction.atomic():
                # Détache ce personnel de tout autre profil existant (contrainte UNIQUE)
                if profil.role.code == 'medecin':
                    Profil.objects.filter(medecin_id=personnel_id).exclude(pk=profil.pk).update(medecin=None)
                    profil.medecin = Medecin.objects.filter(pk=personnel_id).first()
                elif profil.role.code == 'infirmier':
                    Profil.objects.filter(infirmier_id=personnel_id).exclude(pk=profil.pk).update(infirmier=None)
                    profil.infirmier = Infirmier.objects.filter(pk=personnel_id).first()
                elif profil.role.code == 'laborantin':
                    Profil.objects.filter(laborantin_id=personnel_id).exclude(pk=profil.pk).update(laborantin=None)
                    profil.laborantin = Laborantin.objects.filter(pk=personnel_id).first()
                elif profil.role.code == 'receptionniste':
                    Profil.objects.filter(receptionniste_id=personnel_id).exclude(pk=profil.pk).update(receptionniste=None)
                    profil.receptionniste = Receptionniste.objects.filter(pk=personnel_id).first()

        with transaction.atomic():
            user.save()
            profil.save()
        messages.success(request, "Utilisateur mis à jour.")
        return redirect('comptes:utilisateurs_liste')

    return render(request, 'comptes/utilisateur_form.html', {
        'profil': profil,
        'edit_user': user,
        'roles': roles,
        'medecins': Medecin.objects.all(),
        'infirmiers': Infirmier.objects.all(),
        'laborantins': Laborantin.objects.all(),
        'receptionnistes': Receptionniste.objects.all(),
    })


@admin_required
def utilisateur_toggle_actif(request, pk):
    profil = get_object_or_404(Profil, pk=pk)
    if profil.user == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
        return redirect('comptes:utilisateurs_liste')
    if request.method == 'POST':
        profil.user.is_active = not profil.user.is_active
        profil.user.save()
        etat = "activé" if profil.user.is_active else "désactivé"
        messages.success(request, f"Compte {profil.user.username} {etat} avec succès.")
    return redirect('comptes:utilisateurs_liste')


@admin_required
def roles_liste(request):
    roles = Role.objects.prefetch_related('permissions').all()
    return render(request, 'comptes/roles_liste.html', {'roles': roles})


@admin_required
def role_modifier(request, pk):
    role = get_object_or_404(Role, pk=pk)
    permissions = Permission.objects.all()
    if request.method == 'POST':
        role.libelle = request.POST.get('libelle', role.libelle).strip()
        role.description = request.POST.get('description', '').strip()
        ids = request.POST.getlist('permissions')
        role.permissions.set(Permission.objects.filter(pk__in=ids))
        role.save()
        messages.success(request, "Role mis a jour.")
        return redirect('comptes:roles_liste')
    role_perm_ids = set(role.permissions.values_list('id', flat=True))
    return render(request, 'comptes/role_form.html', {
        'role': role,
        'permissions': permissions,
        'role_perm_ids': role_perm_ids,
    })


@admin_required
def permissions_liste(request):
    return render(request, 'comptes/permissions_liste.html', {
        'permissions': Permission.objects.all(),
    })


@admin_required
def utilisateur_reset_password(request, pk):
    profil = get_object_or_404(Profil.objects.select_related('user'), pk=pk)
    user = profil.user
    if request.method == 'POST':
        new_password  = request.POST.get('new_password', '').strip()
        confirm       = request.POST.get('confirm_password', '').strip()
        if not new_password:
            messages.error(request, 'Le mot de passe ne peut pas être vide.')
        elif new_password != confirm:
            messages.error(request, 'Les deux mots de passe ne correspondent pas.')
        elif len(new_password) < 4:
            messages.error(request, 'Le mot de passe doit contenir au moins 4 caractères.')
        else:
            user.set_password(new_password)
            user.save()
            messages.success(request, f'Mot de passe de {user.username} réinitialisé avec succès.')
            return redirect('comptes:utilisateurs_liste')
    return render(request, 'comptes/reset_password.html', {
        'profil': profil,
        'edit_user': user,
    })


def mot_de_passe_oublie(request):
    """Ancienne URL — redirige vers le flux de réinitialisation par email."""
    return redirect('password_reset')


# ── Notifications (cloche de la barre du haut) ─────────────────

@login_required
def notification_ouvrir(request, pk):
    """Marque la notification comme lue puis redirige vers sa cible."""
    notif = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notif.lu:
        notif.lu = True
        notif.save(update_fields=['lu'])
    return redirect(notif.url or 'dashboard')


@login_required
def notifications_liste(request):
    notifs = Notification.objects.filter(user=request.user)
    return render(request, 'comptes/notifications_liste.html', {'notifications': notifs})


@login_required
def notifications_tout_lire(request):
    Notification.objects.filter(user=request.user, lu=False).update(lu=True)
    return redirect(request.META.get('HTTP_REFERER') or 'dashboard')


@admin_required
def journal_audit(request):
    """Journal d'audit : historique des actions sensibles (admin uniquement)."""
    qs = JournalAudit.objects.select_related('user').all()

    action = request.GET.get('action', '').strip()
    modele = request.GET.get('modele', '').strip()
    q = request.GET.get('q', '').strip()
    if action:
        qs = qs.filter(action=action)
    if modele:
        qs = qs.filter(modele=modele)
    if q:
        qs = qs.filter(objet_repr__icontains=q)

    page = Paginator(qs, 50).get_page(request.GET.get('page'))
    return render(request, 'comptes/journal_audit.html', {
        'entrees': page,
        'actions': JournalAudit.ACTION_CHOICES,
        'modeles': JournalAudit.objects.values_list('modele', flat=True).distinct().order_by('modele'),
        'f_action': action,
        'f_modele': modele,
        'q': q,
    })