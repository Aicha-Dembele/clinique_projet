from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from comptes.decorators import role_required, admin_required

from .models import Medecin, Infirmier, Laborantin, AgentAdministratif, Receptionniste


@admin_required
def personnel_liste(request):
    filtre = request.GET.get('filtre', 'tous')
    q      = request.GET.get('q', '').strip()

    medecins        = Medecin.objects.all()
    infirmiers      = Infirmier.objects.all()
    laborantins     = Laborantin.objects.all()
    agents          = AgentAdministratif.objects.all()
    receptionnistes = Receptionniste.objects.all()

    if q:
        medecins        = medecins.filter(nom__icontains=q) | medecins.filter(prenom__icontains=q)
        infirmiers      = infirmiers.filter(nom__icontains=q) | infirmiers.filter(prenom__icontains=q)
        laborantins     = laborantins.filter(nom__icontains=q) | laborantins.filter(prenom__icontains=q)
        receptionnistes = receptionnistes.filter(nom__icontains=q) | receptionnistes.filter(prenom__icontains=q)

    total_medecins   = Medecin.objects.count()
    total_infirmiers = Infirmier.objects.count()
    total_personnel  = total_medecins + total_infirmiers + Laborantin.objects.count() + Receptionniste.objects.count()

    return render(request, 'personnel/liste.html', {
        'medecins':        medecins,
        'infirmiers':      infirmiers,
        'laborantins':     laborantins,
        'agents':          agents,
        'receptionnistes': receptionnistes,
        'filtre':          filtre,
        'q':               q,
        'total_medecins':  total_medecins,
        'total_infirmiers':total_infirmiers,
        'total_personnel': total_personnel,
    })


@admin_required
def medecin_ajouter(request):
    if request.method == "POST":
        try:
            Medecin.objects.create(
                nom=request.POST["nom"],
                prenom=request.POST["prenom"],
                telephone=request.POST["telephone"],
                adresse=request.POST.get("adresse", ""),
                service=request.POST["service"],
                specialite=request.POST["specialite"],
                role="medecin",
                mot_de_passe=request.POST["mot_de_passe"],
            )
            messages.success(request, "Médecin ajouté.")
            return redirect("personnel:liste")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return render(request, "personnel/medecin_form.html", {"action": "Ajouter"})


@admin_required
def medecin_modifier(request, pk):
    medecin = get_object_or_404(Medecin, pk=pk)
    if request.method == "POST":
        medecin.nom = request.POST["nom"]
        medecin.prenom = request.POST["prenom"]
        medecin.telephone = request.POST["telephone"]
        medecin.adresse = request.POST.get("adresse", "")
        medecin.service = request.POST["service"]
        medecin.specialite = request.POST["specialite"]
        medecin.save()
        messages.success(request, "Médecin modifié.")
        return redirect("personnel:liste")
    return render(request, "personnel/medecin_form.html", {"medecin": medecin, "action": "Modifier"})


@admin_required
def medecin_supprimer(request, pk):
    medecin = get_object_or_404(Medecin, pk=pk)
    if request.method == "POST":
        medecin.delete()
        messages.success(request, "Médecin supprimé.")
        return redirect("personnel:liste")
    return render(request, "partials/confirmer_suppression.html", {
        "objet": f"Dr. {medecin.nom} {medecin.prenom}",
        "retour_url": "/personnel/",
    })


@admin_required
def infirmier_ajouter(request):
    if request.method == "POST":
        try:
            Infirmier.objects.create(
                nom=request.POST["nom"],
                prenom=request.POST["prenom"],
                telephone=request.POST["telephone"],
                service=request.POST["service"],
                role="infirmier",
                mot_de_passe=request.POST["mot_de_passe"],
                adresse=request.POST.get("adresse", ""),
            )
            messages.success(request, "Infirmier ajouté.")
            return redirect("personnel:liste")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return render(request, "personnel/infirmier_form.html", {"action": "Ajouter"})


@admin_required
def infirmier_modifier(request, pk):
    infirmier = get_object_or_404(Infirmier, pk=pk)
    if request.method == "POST":
        infirmier.nom = request.POST["nom"]
        infirmier.prenom = request.POST["prenom"]
        infirmier.telephone = request.POST["telephone"]
        infirmier.adresse = request.POST.get("adresse", "")
        infirmier.service = request.POST["service"]
        infirmier.save()
        messages.success(request, "Infirmier modifié.")
        return redirect("personnel:liste")
    return render(request, "personnel/infirmier_form.html", {"infirmier": infirmier, "action": "Modifier"})


@admin_required
def infirmier_supprimer(request, pk):
    infirmier = get_object_or_404(Infirmier, pk=pk)
    if request.method == "POST":
        infirmier.delete()
        messages.success(request, "Infirmier supprimé.")
        return redirect("personnel:liste")
    return render(request, "partials/confirmer_suppression.html", {
        "objet": f"Inf. {infirmier.nom} {infirmier.prenom}",
        "retour_url": "/personnel/",
    })


@admin_required
def laborantin_ajouter(request):
    if request.method == "POST":
        try:
            Laborantin.objects.create(
                nom=request.POST["nom"],
                prenom=request.POST["prenom"],
                telephone=request.POST["telephone"],
                specialite=request.POST["specialite"],
                role="laborantin",
                mot_de_passe=request.POST["mot_de_passe"],
                adresse=request.POST.get("adresse", ""),
                service=request.POST.get("service", "Laboratoire"),
            )
            messages.success(request, "Laborantin ajouté.")
            return redirect("personnel:liste")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return render(request, "personnel/laborantin_form.html", {"action": "Ajouter"})


@admin_required
def laborantin_modifier(request, pk):
    laborantin = get_object_or_404(Laborantin, pk=pk)
    if request.method == "POST":
        laborantin.nom = request.POST["nom"]
        laborantin.prenom = request.POST["prenom"]
        laborantin.telephone = request.POST["telephone"]
        laborantin.adresse = request.POST.get("adresse", "")
        laborantin.specialite = request.POST.get("specialite", "")
        laborantin.service = request.POST.get("service", "Laboratoire")
        laborantin.save()
        messages.success(request, "Laborantin modifié.")
        return redirect("personnel:liste")
    return render(request, "personnel/laborantin_form.html", {"laborantin": laborantin, "action": "Modifier"})


@admin_required
def laborantin_supprimer(request, pk):
    laborantin = get_object_or_404(Laborantin, pk=pk)
    if request.method == "POST":
        laborantin.delete()
        messages.success(request, "Laborantin supprimé.")
        return redirect("personnel:liste")
    return render(request, "partials/confirmer_suppression.html", {
        "objet": f"{laborantin.nom} {laborantin.prenom}",
        "retour_url": "/personnel/",
    })


@admin_required
def receptionniste_ajouter(request):
    if request.method == "POST":
        try:
            Receptionniste.objects.create(
                nom=request.POST["nom"],
                prenom=request.POST["prenom"],
                telephone=request.POST["telephone"],
                role="receptionniste",
                mot_de_passe=request.POST["mot_de_passe"],
                adresse=request.POST.get("adresse", ""),
                service="Accueil",
            )
            messages.success(request, "Réceptionniste ajouté.")
            return redirect("personnel:liste")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")
    return render(request, "personnel/receptionniste_form.html", {"action": "Ajouter"})


@admin_required
def receptionniste_modifier(request, pk):
    receptionniste = get_object_or_404(Receptionniste, pk=pk)
    if request.method == "POST":
        receptionniste.nom = request.POST["nom"]
        receptionniste.prenom = request.POST["prenom"]
        receptionniste.telephone = request.POST["telephone"]
        receptionniste.adresse = request.POST.get("adresse", "")
        receptionniste.service = request.POST.get("service", "Accueil")
        receptionniste.save()
        messages.success(request, "Réceptionniste modifié.")
        return redirect("personnel:liste")
    return render(request, "personnel/receptionniste_form.html", {"receptionniste": receptionniste, "action": "Modifier"})


@admin_required
def receptionniste_supprimer(request, pk):
    receptionniste = get_object_or_404(Receptionniste, pk=pk)
    if request.method == "POST":
        receptionniste.delete()
        messages.success(request, "Réceptionniste supprimé.")
        return redirect("personnel:liste")
    return render(request, "partials/confirmer_suppression.html", {
        "objet": f"{receptionniste.nom} {receptionniste.prenom}",
        "retour_url": "/personnel/",
    })