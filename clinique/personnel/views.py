from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .models import Medecin, Infirmier, Laborantin, AgentAdministratif, Receptionniste


@login_required
def personnel_liste(request):
    return render(request, "personnel/liste.html", {
        "medecins":        Medecin.objects.all(),
        "infirmiers":      Infirmier.objects.all(),
        "laborantins":     Laborantin.objects.all(),
        "agents":          AgentAdministratif.objects.all(),
        "receptionnistes": Receptionniste.objects.all(),
    })


@login_required
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


@login_required
def medecin_modifier(request, pk):
    medecin = get_object_or_404(Medecin, pk=pk)
    if request.method == "POST":
        medecin.nom = request.POST["nom"]
        medecin.prenom = request.POST["prenom"]
        medecin.telephone = request.POST["telephone"]
        medecin.service = request.POST["service"]
        medecin.specialite = request.POST["specialite"]
        medecin.save()
        messages.success(request, "Médecin modifié.")
        return redirect("personnel:liste")
    return render(request, "personnel/medecin_form.html", {"medecin": medecin, "action": "Modifier"})


@login_required
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


@login_required
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


@login_required
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


@login_required
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
