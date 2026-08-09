"""
Fichier WSGI pour PythonAnywhere — Clinique Nevroglie.

Ce fichier est copié vers /var/www/ggroupe3_pythonanywhere_com_wsgi.py
C'est lui que le serveur exécute pour démarrer l'application.

Il ne contient AUCUN secret : la clé secrète est lue depuis
~/.django_secret_key, un fichier qui reste sur le serveur et n'est
jamais versionné.
"""

import os
import sys

HOME = os.path.expanduser('~')

# ── 1. Dossier du projet (celui qui contient manage.py) ──────────────
path = os.path.join(HOME, 'clinique_projet', 'clinique')
if path not in sys.path:
    sys.path.insert(0, path)

# ── 2. Filet de sécurité : bibliothèques de l'environnement virtuel ──
# Normalement le champ « Virtualenv » de l'onglet Web suffit. Ceci
# permet au site de fonctionner même si ce champ est mal renseigné.
for version in ('3.13', '3.12', '3.11'):
    site_packages = os.path.join(
        HOME, '.virtualenvs', 'clinique-venv', 'lib',
        'python' + version, 'site-packages',
    )
    if os.path.isdir(site_packages) and site_packages not in sys.path:
        sys.path.insert(0, site_packages)
        break

# ── 3. Réglages de production ────────────────────────────────────────
# settings.py lit ces variables ; les valeurs par défaut du fichier
# (DEBUG=True, etc.) ne conviennent qu'au développement local.
key_file = os.path.join(HOME, '.django_secret_key')
if os.path.exists(key_file):
    with open(key_file) as f:
        os.environ['DJANGO_SECRET_KEY'] = f.read().strip()

os.environ['DJANGO_DEBUG'] = 'False'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'ggroupe3.pythonanywhere.com'
os.environ['DJANGO_CSRF_TRUSTED_ORIGINS'] = 'https://ggroupe3.pythonanywhere.com'
os.environ['DJANGO_SETTINGS_MODULE'] = 'clinique.settings'

# ── 4. Démarrage de Django ───────────────────────────────────────────
from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
