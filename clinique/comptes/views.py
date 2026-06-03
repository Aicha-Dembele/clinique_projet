from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required

from .models import Profil, Role, Permission
from .decorators import admin_required, role_required
from personnel.models import Medecin, Infirmier, Laborantin, Receptionniste


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
                if role.code == 'medecin':
                    profil.medecin = Medecin.objects.filter(pk=personnel_id).first()
                elif role.code == 'infirmier':
                    profil.infirmier = Infirmier.objects.filter(pk=personnel_id).first()
                elif role.code == 'laborantin':
                    profil.laborantin = Laborantin.objects.filter(pk=personnel_id).first()
                elif role.code == 'receptionniste':
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
            if profil.role.code == 'medecin':
                profil.medecin = Medecin.objects.filter(pk=personnel_id).first()
            elif profil.role.code == 'infirmier':
                profil.infirmier = Infirmier.objects.filter(pk=personnel_id).first()
            elif profil.role.code == 'laborantin':
                profil.laborantin = Laborantin.objects.filter(pk=personnel_id).first()
            elif profil.role.code == 'receptionniste':
                profil.receptionniste = Receptionniste.objects.filter(pk=personnel_id).first()

        with transaction.atomic():
            user.save()
            profil.save()
        messages.success(request, "Utilisateur mis a jour.")
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
def utilisateur_supprimer(request, pk):
    profil = get_object_or_404(Profil, pk=pk)
    if request.method == 'POST':
        if profil.user == request.user:
            messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
            return redirect('comptes:utilisateurs_liste')
        profil.user.delete()
        messages.success(request, "Utilisateur supprime.")
        return redirect('comptes:utilisateurs_liste')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet': profil.user.username,
        'cancel_url': 'comptes:utilisateurs_liste',
    })


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
