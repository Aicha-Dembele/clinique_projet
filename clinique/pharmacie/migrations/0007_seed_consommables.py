# Données de départ : consommables, solutés de perfusion et antiseptiques.
from django.db import migrations


# nom, dci, dosage, forme, categorie, unite, prix, stock, seuil, commun, indication
ARTICLES = [
    # ── Solutés / Perfusion (prescriptibles → communs) ──
    ("Sérum physiologique", "NaCl 0,9%", "500 ml", "poche", "solute", "poche", 1000, 80, 20, True,
     "Soluté de réhydratation et de rinçage ; perfusion et dilution de médicaments."),
    ("Sérum physiologique", "NaCl 0,9%", "1000 ml", "poche", "solute", "poche", 1500, 50, 15, True,
     "Soluté de réhydratation (grand format) ; perfusion et dilution de médicaments."),
    ("Sérum glucosé 5%", "Glucose 5%", "500 ml", "poche", "solute", "poche", 1200, 60, 15, True,
     "Apport hydrique et énergétique (glucose) par perfusion."),
    ("Ringer lactate", "Ringer lactate", "500 ml", "poche", "solute", "poche", 1500, 40, 10, True,
     "Soluté de remplissage et de rééquilibrage hydro-électrolytique."),
    ("Eau pour préparation injectable", "EPPI", "10 ml", "ampoule", "solute", "ampoule", 300, 200, 50, True,
     "Solvant pour reconstitution des médicaments injectables."),
    # ── Antiseptiques / Désinfectants (communs) ──
    ("Povidone iodée (Bétadine)", "Povidone iodée 10%", "125 ml", "flacon", "antiseptique", "flacon", 2000, 30, 10, True,
     "Antiseptique cutané ; désinfection des plaies et de la peau avant un geste."),
    ("Alcool éthylique 70°", "Éthanol 70°", "250 ml", "flacon", "antiseptique", "flacon", 1000, 40, 10, True,
     "Désinfection de la peau saine."),
    ("Eau oxygénée 10 volumes", "Peroxyde d'hydrogène", "250 ml", "flacon", "antiseptique", "flacon", 800, 30, 10, True,
     "Antiseptique et nettoyage des plaies."),
    # ── Consommables / Matériel médical (stock seulement) ──
    ("Seringue", "", "2 ml", "", "consommable", "pièce", 100, 300, 50, False, "Injection et prélèvement."),
    ("Seringue", "", "5 ml", "", "consommable", "pièce", 150, 300, 50, False, "Injection et prélèvement."),
    ("Seringue", "", "10 ml", "", "consommable", "pièce", 200, 200, 50, False, "Injection et prélèvement."),
    ("Aiguille stérile", "", "21G", "", "consommable", "pièce", 100, 300, 50, False, "Injection IM / IV."),
    ("Compresses stériles", "", "10 x 10 cm", "sachet", "consommable", "sachet", 250, 150, 30, False,
     "Pansement et nettoyage des plaies."),
    ("Coton hydrophile", "", "100 g", "rouleau", "consommable", "rouleau", 700, 60, 15, False, "Soins et nettoyage."),
    ("Bande de gaze", "", "5 m", "rouleau", "consommable", "rouleau", 400, 80, 20, False, "Maintien des pansements."),
    ("Sparadrap", "", "", "rouleau", "consommable", "rouleau", 500, 70, 15, False, "Fixation des pansements."),
    ("Gants d'examen", "", "", "", "consommable", "boîte", 3500, 40, 10, False, "Protection lors des soins (boîte de 100)."),
    ("Perfuseur", "", "set", "", "consommable", "pièce", 600, 100, 20, False, "Dispositif de pose de perfusion."),
    ("Masque chirurgical", "", "", "", "consommable", "boîte", 2500, 30, 10, False, "Protection (boîte de 50)."),
]


def seed(apps, schema_editor):
    Medicament = apps.get_model('pharmacie', 'Medicament')
    for nom, dci, dosage, forme, cat, unite, prix, stock, seuil, commun, indic in ARTICLES:
        obj, cree = Medicament.objects.get_or_create(
            nom=nom, dosage=dosage,
            defaults=dict(dci=dci, forme=forme, categorie=cat, unite=unite,
                          prix_unitaire=prix, quantite_stock=stock, seuil_alerte=seuil,
                          commun=commun, indication=indic, actif=True))
        if not cree:
            obj.categorie = cat
            obj.indication = indic
            obj.save()


def unseed(apps, schema_editor):
    Medicament = apps.get_model('pharmacie', 'Medicament')
    for nom, dci, dosage, *_ in ARTICLES:
        Medicament.objects.filter(nom=nom, dosage=dosage).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacie', '0006_alter_medicament_categorie'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
