from django.db import migrations


MEDICAMENTS = [
    # nom, dci, forme, dosage, categorie, unite, prix, stock, seuil
    ("Doliprane",   "Paracétamol",   "Comprimé", "500 mg",   "antalgique",        "boîte", 1000, 80, 20),
    ("Efferalgan",  "Paracétamol",   "Comprimé", "1 g",      "antipyretique",     "boîte", 1500, 40, 15),
    ("Ibuprofène",  "Ibuprofène",    "Comprimé", "400 mg",   "anti_inflammatoire","boîte", 1200, 30, 10),
    ("Amoxicilline","Amoxicilline",  "Gélule",   "500 mg",   "antibiotique",      "boîte", 2500, 25, 10),
    ("Augmentin",   "Amox.+Ac. clav.","Comprimé","1 g",      "antibiotique",      "boîte", 4500, 12,  8),
    ("Coartem",     "Artéméther+Luméfantrine","Comprimé","20/120 mg","antipaludique","boîte", 3000, 18, 10),
    ("Métronidazole","Métronidazole","Comprimé", "250 mg",   "antibiotique",      "boîte", 1500, 22, 10),
    ("Oméprazole",  "Oméprazole",    "Gélule",   "20 mg",    "digestif",          "boîte", 2000, 14,  8),
    ("Ventoline",   "Salbutamol",    "Aérosol",  "100 µg",   "respiratoire",      "flacon",3500,  9,  5),
    ("Vitamine C",  "Acide ascorbique","Comprimé","500 mg",  "vitamine",          "boîte", 800, 60, 20),
]


def seed(apps, schema_editor):
    Medicament = apps.get_model('pharmacie', 'Medicament')
    for nom, dci, forme, dosage, cat, unite, prix, stock, seuil in MEDICAMENTS:
        Medicament.objects.get_or_create(
            nom=nom,
            defaults={
                'dci': dci, 'forme': forme, 'dosage': dosage, 'categorie': cat,
                'unite': unite, 'prix_unitaire': prix, 'quantite_stock': stock,
                'seuil_alerte': seuil, 'actif': True,
            },
        )


def unseed(apps, schema_editor):
    Medicament = apps.get_model('pharmacie', 'Medicament')
    Medicament.objects.filter(nom__in=[m[0] for m in MEDICAMENTS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacie', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
