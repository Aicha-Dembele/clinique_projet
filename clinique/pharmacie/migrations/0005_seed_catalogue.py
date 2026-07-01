# Données de départ : spécialités + indications + catalogue par spécialité.
from django.db import migrations


# Médicaments déjà présents → indication thérapeutique + médicament « commun »
EXISTANTS = {
    'Doliprane':     "Antalgique et antipyrétique (paracétamol). Douleurs légères à modérées et fièvre.",
    'Efferalgan':    "Antipyrétique et antalgique (paracétamol). Fièvre, douleurs courantes.",
    'Ibuprofène':    "Anti-inflammatoire non stéroïdien (AINS). Douleurs, inflammation, fièvre.",
    'Amoxicilline':  "Antibiotique (pénicilline). Infections ORL, respiratoires, urinaires, dentaires.",
    'Augmentin':     "Antibiotique (amoxicilline + acide clavulanique). Infections bactériennes résistantes.",
    'Coartem':       "Antipaludique (artéméther + luméfantrine). Traitement de l'accès palustre simple.",
    'Métronidazole': "Antibiotique / antiparasitaire. Infections digestives et gynécologiques (vaginose, trichomonas).",
    'Oméprazole':    "Anti-ulcéreux (IPP). Reflux gastro-œsophagien, ulcères, gastrites.",
    'Ventoline':     "Bronchodilatateur (salbutamol). Crise d'asthme, gêne respiratoire.",
    'Vitamine C':    "Complément vitaminique. Fatigue, soutien de l'immunité.",
}

# Catalogue par spécialité : nom, dci, dosage, forme, catégorie, prix, indication, [codes spécialité]
CATALOGUE = [
    # ── Cardiologie ──
    ("Amlodipine",    "Amlodipine",    "5 mg",  "comprimé", "cardiovasculaire", 1500,
     "Antihypertenseur (inhibiteur calcique). Hypertension artérielle, angine de poitrine.", ["cardiologie"]),
    ("Bisoprolol",    "Bisoprolol",    "5 mg",  "comprimé", "cardiovasculaire", 2000,
     "Bêtabloquant. Hypertension, insuffisance cardiaque, troubles du rythme.", ["cardiologie"]),
    ("Furosémide",    "Furosémide",    "40 mg", "comprimé", "cardiovasculaire", 1200,
     "Diurétique de l'anse. Œdèmes, insuffisance cardiaque, hypertension.", ["cardiologie"]),
    ("Atorvastatine", "Atorvastatine", "20 mg", "comprimé", "cardiovasculaire", 3000,
     "Hypolipémiant (statine). Excès de cholestérol, prévention cardiovasculaire.", ["cardiologie"]),
    # ── Neurologie ──
    ("Carbamazépine", "Carbamazépine", "200 mg", "comprimé", "autre", 2500,
     "Antiépileptique. Épilepsie, névralgies (ex. névralgie du trijumeau).", ["neurologie"]),
    ("Lévétiracétam", "Lévétiracétam", "500 mg", "comprimé", "autre", 5000,
     "Antiépileptique. Traitement des crises d'épilepsie.", ["neurologie"]),
    ("Amitriptyline", "Amitriptyline", "25 mg",  "comprimé", "autre", 2000,
     "Douleurs neuropathiques, migraine de fond, dépression.", ["neurologie"]),
    ("Sumatriptan",   "Sumatriptan",   "50 mg",  "comprimé", "autre", 4000,
     "Antimigraineux. Traitement de la crise de migraine.", ["neurologie"]),
    # ── Gynécologie ──
    ("Acide folique",   "Acide folique", "5 mg",   "comprimé", "vitamine",       1000,
     "Vitamine B9. Grossesse : prévention des anomalies du tube neural ; anémie.", ["gynecologie"]),
    ("Sulfate ferreux", "Fer",           "200 mg", "comprimé", "vitamine",       1500,
     "Fer. Anémie ferriprive, notamment pendant la grossesse.", ["gynecologie"]),
    ("Fluconazole",     "Fluconazole",   "150 mg", "gélule",   "autre",          2000,
     "Antifongique. Mycoses vaginales (candidoses).", ["gynecologie"]),
    ("Clotrimazole",    "Clotrimazole",  "200 mg", "ovule",    "dermatologique", 2500,
     "Antifongique local. Mycoses vaginales.", ["gynecologie"]),
]

SPECIALITES = [
    ('generaliste', 'Médecine générale'),
    ('gynecologie', 'Gynécologie'),
    ('cardiologie', 'Cardiologie'),
    ('neurologie',  'Neurologie'),
]


def seed(apps, schema_editor):
    Specialite = apps.get_model('pharmacie', 'Specialite')
    Medicament = apps.get_model('pharmacie', 'Medicament')

    specs = {}
    for code, nom in SPECIALITES:
        specs[code], _ = Specialite.objects.get_or_create(code=code, defaults={'nom': nom})

    # Médicaments existants : indication + marqués « communs » (médicaments de base)
    for nom, indic in EXISTANTS.items():
        Medicament.objects.filter(nom=nom).update(indication=indic, commun=True)
    # Le métronidazole est aussi un médicament de gynécologie
    for m in Medicament.objects.filter(nom='Métronidazole'):
        m.specialites.add(specs['gynecologie'])

    # Catalogue par spécialité
    for nom, dci, dosage, forme, cat, prix, indic, codes in CATALOGUE:
        m, cree = Medicament.objects.get_or_create(
            nom=nom, dosage=dosage,
            defaults=dict(dci=dci, forme=forme, categorie=cat, prix_unitaire=prix,
                          indication=indic, commun=False, unite='boîte',
                          seuil_alerte=5, quantite_stock=30, actif=True))
        if not cree:
            m.indication = indic
            m.save()
        m.specialites.set([specs[c] for c in codes])


def unseed(apps, schema_editor):
    Specialite = apps.get_model('pharmacie', 'Specialite')
    Specialite.objects.filter(code__in=[c for c, _ in SPECIALITES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacie', '0004_specialite_medicament_commun_medicament_indication_and_more'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
