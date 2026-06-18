# Clinique Nevroglie — Logiciel de gestion de clinique

Application web Django de gestion d'une clinique : patients, personnel,
rendez-vous, dossiers médicaux, consultations, examens & résultats,
ordonnances, hospitalisations, traitements, facturation (avec assurance
AMO), pharmacie/stock, rôles & permissions et tableaux de bord.

## Stack technique

- **Python** 3.14 · **Django** 6.0
- Base de données : SQLite (développement)
- Frontend : templates Django + Bootstrap + Chart.js

## Installation (développement)

```bash
# 1. Cloner puis créer l'environnement virtuel
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Appliquer les migrations
cd clinique
python manage.py migrate

# 4. Créer les rôles par défaut puis un compte admin
python manage.py setup_roles
python manage.py createsuperuser

# 5. Lancer le serveur
python manage.py runserver
```

L'application est alors disponible sur http://127.0.0.1:8000/.

## Configuration (variables d'environnement)

Par défaut, le projet fonctionne en mode développement sans configuration.
Pour la **production**, définir les variables suivantes (jamais en clair dans
le dépôt) :

| Variable | Rôle | Défaut (dev) |
|----------|------|--------------|
| `DJANGO_SECRET_KEY` | Clé secrète Django | clé de dev (à régénérer) |
| `DJANGO_DEBUG` | Mode debug (`False` en prod) | `True` |
| `DJANGO_ALLOWED_HOSTS` | Hôtes autorisés, séparés par des virgules | `localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Origines HTTPS de confiance | *(vide)* |
| `DJANGO_TIME_ZONE` | Fuseau horaire | `Africa/Bamako` |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | SMTP pour la réinitialisation de mot de passe | — |

> En production (`DJANGO_DEBUG=False`), le durcissement de sécurité s'active
> automatiquement (HTTPS forcé, cookies sécurisés, HSTS, anti-clickjacking).

Les secrets locaux peuvent aussi être placés dans
`clinique/clinique/local_settings.py` (non versionné).

## Tests

```bash
cd clinique
python manage.py test
```

## Structure des applications

| App | Rôle |
|-----|------|
| `comptes` | Authentification, rôles, permissions, notifications |
| `patients` | Dossiers patients et assurance |
| `personnel` | Médecins, infirmiers, laborantins, réceptionnistes |
| `consultation` | RDV, consultations, examens, résultats, ordonnances, hospitalisations |
| `facturation` | Tarifs, factures, paiements, part assurance (AMO) |
| `pharmacie` | Médicaments, mouvements de stock, dispensation |
