# Déploiement sur PythonAnywhere (offre gratuite)

Guide pas à pas pour mettre en ligne la Clinique Nevroglie **sans perdre aucune donnée**.

Remplace partout `TONUSER` par ton nom d'utilisateur PythonAnywhere.

---

## Ce qu'il faut savoir avant de commencer

| Point | Détail |
|---|---|
| Base de données | On garde **SQLite** (le fichier `db.sqlite3` est copié tel quel → 0 perte). MySQL n'est plus dans l'offre gratuite depuis janvier 2026. |
| Python | Choisir **3.13** (Django 6.0.5 exige 3.12 minimum). |
| Adresse du site | `https://TONUSER.pythonanywhere.com` — HTTPS gratuit inclus. |
| Expiration | L'app gratuite **expire après 1 mois** sans activité. Un bouton « Run until… » sur l'onglet *Web* la réactive. **À cliquer la veille de la soutenance.** |
| Emails | L'offre gratuite bloque le SMTP, **sauf Gmail** — la réinitialisation de mot de passe devrait donc marcher, mais peut être capricieuse. |
| Stripe | Les appels vers `api.stripe.com` peuvent être bloqués par le pare-feu gratuit. À tester ; si bloqué, demander l'ajout à la liste blanche sur le forum PythonAnywhere. |

---

## Étape 1 — Envoyer le code sur GitHub

Sur ton PC, dans `clinique_project` :

```bash
git add -A
git commit -m "Version deployee sur PythonAnywhere"
git push origin aicha
```

> `db.sqlite3`, `media/` et `local_settings.py` sont dans `.gitignore` : ils ne partent **pas** sur GitHub (c'est voulu, ils contiennent tes données et ton mot de passe Gmail). On les transférera à la main à l'étape 6.

---

## Étape 2 — Créer le compte

Sur https://www.pythonanywhere.com → **Pricing & signup** → **Create a Beginner account** (gratuit, pas de carte bancaire).

Note bien ton nom d'utilisateur : il devient l'adresse de ton site.

---

## Étape 3 — Récupérer le code sur le serveur

Onglet **Consoles** → **Bash**. Puis :

```bash
git clone https://github.com/Aicha-Dembele/clinique_projet.git
cd clinique_projet
git checkout aicha
```

---

## Étape 4 — Installer les bibliothèques

Toujours dans la console Bash :

```bash
mkvirtualenv --python=/usr/bin/python3.13 clinique-venv
pip install Django==6.0.5 tzdata reportlab==4.4.10 Pillow==12.0.0 stripe==11.4.1
```

> On n'installe **pas** `mysqlclient` : le projet tourne sur SQLite, et ce paquet échouerait à s'installer.

Génère aussi une nouvelle clé secrète (à garder de côté pour l'étape 5) :

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Étape 5 — Configurer l'application web

Onglet **Web** → **Add a new web app** → **Manual configuration** (surtout **pas** « Django ») → **Python 3.13**.

### 5a. Virtualenv

Section *Virtualenv*, saisir :

```
/home/TONUSER/.virtualenvs/clinique-venv
```

### 5b. Fichier WSGI

Section *Code* → cliquer sur le lien `/var/www/TONUSER_pythonanywhere_com_wsgi.py`.
**Effacer tout** le contenu et le remplacer par :

```python
import os
import sys

# Dossier qui contient manage.py
path = '/home/TONUSER/clinique_projet/clinique'
if path not in sys.path:
    sys.path.insert(0, path)

# Réglages de production
os.environ['DJANGO_SECRET_KEY'] = 'COLLER_ICI_LA_CLE_DE_L_ETAPE_4'
os.environ['DJANGO_DEBUG'] = 'False'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'TONUSER.pythonanywhere.com'
os.environ['DJANGO_CSRF_TRUSTED_ORIGINS'] = 'https://TONUSER.pythonanywhere.com'

os.environ['DJANGO_SETTINGS_MODULE'] = 'clinique.settings'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Puis **Save**.

### 5c. Fichiers statiques et médias

Section *Static files*, ajouter **deux** lignes :

| URL | Directory |
|---|---|
| `/static/` | `/home/TONUSER/clinique_projet/clinique/staticfiles` |
| `/media/` | `/home/TONUSER/clinique_projet/clinique/media` |

---

## Étape 6 — Transférer les données (l'étape « zéro perte »)

Onglet **Files**, naviguer dans `clinique_projet/clinique/`, puis **Upload a file** :

1. `db.sqlite3` — depuis `C:\Users\User\clinique_project\clinique\db.sqlite3` (≈ 750 Ko)
   → à déposer dans `/home/TONUSER/clinique_projet/clinique/`
2. Le dossier `media/` — créer `media/patients/photos/` via *New directory*, puis y téléverser les photos.
3. `local_settings.py` — depuis `C:\Users\User\clinique_project\clinique\clinique\`
   → à déposer dans `/home/TONUSER/clinique_projet/clinique/clinique/`
   (c'est lui qui contient le mot de passe d'application Gmail)

> **Ordre important :** téléverser `db.sqlite3` **avant** toute commande `migrate` ou `createsuperuser`, sinon tu risques d'écraser tes données par une base vide.

---

## Étape 7 — Fichiers statiques et vérification

Retour dans la console Bash :

```bash
cd ~/clinique_projet/clinique
workon clinique-venv
python manage.py collectstatic --noinput
python manage.py migrate
python manage.py check --deploy
```

`migrate` doit répondre « No migrations to apply » : c'est la preuve que ta base est bien celle de ton PC, intacte.

---

## Étape 8 — Mise en ligne

Onglet **Web** → gros bouton vert **Reload**.

Ouvrir `https://TONUSER.pythonanywhere.com` et se connecter avec tes identifiants habituels (ils sont dans la base transférée).

---

## En cas de problème

| Symptôme | Cause probable | Solution |
|---|---|---|
| Page « Something went wrong » | Erreur Python | Onglet *Web* → **Error log** → lire les dernières lignes |
| `DisallowedHost` | `DJANGO_ALLOWED_HOSTS` mal orthographié | Corriger le fichier WSGI puis **Reload** |
| Site sans mise en forme (texte brut) | `collectstatic` non lancé ou mapping `/static/` faux | Refaire l'étape 7 puis 5c |
| Photos patients cassées | Dossier `media/` non téléversé | Refaire l'étape 6.2 |
| Boucle de redirection infinie | HTTPS mal détecté | Vérifier que `SECURE_PROXY_SSL_HEADER` est bien dans `settings.py` (il y est déjà) |
| `CSRF verification failed` à la connexion | `DJANGO_CSRF_TRUSTED_ORIGINS` oublié ou sans `https://` | Corriger le fichier WSGI puis **Reload** |

---

## Mettre à jour le site plus tard

```bash
cd ~/clinique_projet
git pull
cd clinique
workon clinique-venv
python manage.py migrate
python manage.py collectstatic --noinput
```

Puis **Reload** sur l'onglet *Web*. Tes données ne sont jamais touchées par un `git pull`.
