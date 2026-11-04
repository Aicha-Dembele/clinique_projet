# Déploiement sur PythonAnywhere (offre gratuite)

Guide pas à pas pour mettre en ligne la Clinique Nevroglie **sans perdre aucune donnée**.

Compte PythonAnywhere : **clinique** (écrit en minuscules) — site : https://clinique.pythonanywhere.com

> ## ✅ Déploiement réalisé le 4 novembre 2026
>
> Le site est en ligne : **https://clinique.pythonanywhere.com**
>
> Il remplace l'ancien compte `GGROUPE3`, devenu inaccessible.
>
> Base envoyée depuis le PC : `db.sqlite3`, empreinte SHA-256 identique des deux
> côtés avant `migrate`. Elle contient 12 comptes, le personnel, les tarifs et
> 41 médicaments, mais **aucun patient**.
>
> ⚠️ **Tous les mois** : onglet *Web* → bouton **« Run until 1 month from today »**.
> Sans ce clic, le site est désactivé le **4 décembre 2026**. PythonAnywhere
> envoie un rappel par email une semaine avant.

---

## Ce qu'il faut savoir avant de commencer

| Point | Détail |
|---|---|
| Base de données | On garde **SQLite** (le fichier `db.sqlite3` est copié tel quel → 0 perte). MySQL n'est plus dans l'offre gratuite depuis janvier 2026. |
| Python | Choisir **3.13** (Django 6.0.5 exige 3.12 minimum). |
| Adresse du site | `https://clinique.pythonanywhere.com` — HTTPS gratuit inclus. L'adresse reprend le nom du compte. L'offre gratuite n'accepte pas de domaine personnel (à partir de l'offre Developer, 10 $/mois). |
| Expiration | L'app gratuite **expire après 1 mois**. Le bouton « Run until… » de l'onglet *Web* la prolonge. |
| Emails | L'offre gratuite bloque le SMTP, **sauf Gmail** — la réinitialisation de mot de passe devrait donc marcher, mais peut être capricieuse. |
| SAMA Money | Sans clé, l'application reste en mode démonstration. Avec une clé, les appels vers `api.sama.money` peuvent être bloqués par le pare-feu gratuit : à tester. |

---

## Étape 1 — Envoyer le code sur GitHub

Sur ton PC, dans `clinique_project` :

```bash
git add -A
git commit -m "Version deployee sur PythonAnywhere"
git push origin main
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
```

---

## Étape 4 — Installer les bibliothèques

Toujours dans la console Bash :

```bash
mkvirtualenv --python=/usr/bin/python3.13 clinique-venv
pip install -r ~/clinique_projet/requirements.txt
```

> `mysqlclient` n'est **pas** installé : il est commenté dans `requirements.txt`, car le serveur tourne sur SQLite.

---

## Étape 5 — Configurer l'application web

Onglet **Web** → **Add a new web app** → **Manual configuration** (surtout **pas** « Django ») → **Python 3.13**.

### 5a. Virtualenv

Section *Virtualenv*, saisir :

```
/home/clinique/.virtualenvs/clinique-venv
```

### 5b. Fichier WSGI

Le fichier est versionné dans `deploy/wsgi_pythonanywhere.py`. Il déduit l'adresse du
site du nom du compte : il n'y a rien à modifier dedans. On le copie en place depuis
la console Bash, **après** avoir créé l'application web :

```bash
workon clinique-venv
python -c "import os; from django.core.management.utils import get_random_secret_key as g; open(os.path.expanduser('~/.django_secret_key'),'w').write(g())"
chmod 600 ~/.django_secret_key
cp ~/clinique_projet/deploy/wsgi_pythonanywhere.py /var/www/clinique_pythonanywhere_com_wsgi.py
```

La clé secrète est générée **sur le serveur** et stockée dans
`~/.django_secret_key` (hors dépôt, permissions 600) ; le fichier WSGI la lit
au démarrage. Elle n'a donc jamais transité par GitHub.

### 5c. Fichiers statiques et médias

Section *Static files*, ajouter **deux** lignes :

| URL | Directory |
|---|---|
| `/static/` | `/home/clinique/clinique_projet/clinique/staticfiles` |
| `/media/` | `/home/clinique/clinique_projet/clinique/media` |

---

## Étape 6 — Transférer les données (l'étape « zéro perte »)

Onglet **Files**, naviguer dans `clinique_projet/clinique/`, puis **Upload a file** :

1. `db.sqlite3` — depuis `C:\Users\User\clinique_project\clinique\db.sqlite3` (≈ 840 Ko)
   → à déposer dans `/home/clinique/clinique_projet/clinique/`
2. Le dossier `media/` — seulement si la base envoyée contient des patients : créer `media/patients/photos/` via *New directory*, puis y téléverser les photos.
3. `local_settings.py` — **à créer sur place, surtout pas à téléverser** (voir ci-dessous).

> **Ordre important :** téléverser `db.sqlite3` **avant** toute commande `migrate` ou `createsuperuser`, sinon tu risques d'écraser tes données par une base vide.

### 6b. Créer `local_settings.py` sur le serveur (envoi des emails)

⚠️ **Ne jamais téléverser le `local_settings.py` du PC.** Celui-ci contient le bloc
de configuration MySQL (`127.0.0.1:3307`), qui n'existe pas sur PythonAnywhere :
le site tomberait en panne au premier accès à la base. Sur le serveur, ce fichier
ne doit contenir **que** les réglages email.

Onglet **Files** → naviguer dans `clinique_projet/clinique/clinique/` (le dossier
qui contient `settings.py`) → champ *Enter new file name* : `local_settings.py`
→ bouton **New file**. Y coller uniquement :

> Si le bouton répond « **Cannot create file: Already exists** », le fichier est
> déjà là : cliquer sur son nom pour l'ouvrir, et vérifier qu'il contient bien les
> trois lignes ci-dessous. Un fichier présent mais sans `EMAIL_HOST_PASSWORD`
> produit exactement la même panne qu'un fichier absent.

```python
EMAIL_HOST_USER = "aichadembele524@gmail.com"
DEFAULT_FROM_EMAIL = "Clinique Nevroglie <aichadembele524@gmail.com>"
EMAIL_HOST_PASSWORD = "les16caracteres"
```

Les 16 caractères sont le **mot de passe d'application Gmail** ; ils se recopient
depuis le `local_settings.py` du PC. Puis **Save**, et **Reload** sur l'onglet *Web*.

> Sans ce fichier, `settings.py` retombe sur ses valeurs par défaut : expéditeur
> `nanadiawra15@gmail.com` et mot de passe vide. Gmail refuse alors l'envoi avec
> `SMTPSenderRefused: 530 5.7.0 Authentication Required` — et la fonction
> « mot de passe oublié » échoue **en silence** : la page affiche bien sa
> confirmation, mais aucun email ne part jamais.

Vérification (console **Bash**) — la commande ne doit rien afficher et l'email
doit arriver :

```bash
cd ~/clinique_projet/clinique && workon clinique-venv && python manage.py sendtestemail TON_ADRESSE@gmail.com
```

> Le fichier est dans `.gitignore` : il ne partira jamais sur GitHub, ce qui est
> indispensable puisque le dépôt est **public**.

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

`migrate` applique seulement les mises à jour que la base n'a pas encore (10 lors du déploiement du 4 novembre), sans effacer de données. Une seule modifie du contenu : `0022_retirer_takaful` retire Takaful des patients et rend inactive une formule déjà portée par des factures.

---

## Étape 8 — Mise en ligne

Onglet **Web** → gros bouton vert **Reload**.

Ouvrir `https://clinique.pythonanywhere.com` et se connecter avec tes identifiants habituels (ils sont dans la base transférée).

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
| « Mot de passe oublié » : la page confirme l'envoi mais aucun email n'arrive | `local_settings.py` absent sur le serveur → Gmail refuse (`530 Authentication Required`) | Faire l'**étape 6b**, puis **Reload** |
| Toujours aucun email alors que `sendtestemail` fonctionne | Le compte visé n'a pas d'adresse en base, ou porte une autre adresse que celle tapée | *Utilisateurs* → **Modifier** → corriger le champ **Email**. L'application n'envoie qu'aux comptes **actifs** dont l'adresse correspond (les majuscules ne comptent pas), sinon elle affiche quand même sa page de confirmation (protection anti-énumération) |

---

## Mettre à jour le site plus tard

```bash
cd ~/clinique_projet
git pull
workon clinique-venv
pip install -r requirements.txt
cd clinique
python manage.py migrate
python manage.py collectstatic --noinput
```

Puis **Reload** sur l'onglet *Web*. Tes données ne sont jamais touchées par un `git pull`.

---

## Mise à jour « paiement avant soins » — une étape en plus, une seule fois

Le logiciel exige désormais que la facture soit **réglée avant** la
consultation, l'examen et l'hospitalisation (voir la section *Protocole de
soin* du `README.md`).

La base en ligne contient des rendez-vous, des examens et des hospitalisations
enregistrés **avant** cette règle : ils n'ont pas de facture, donc plus rien
n'est réalisable pour eux — le médecin ne peut plus enregistrer leur
consultation, le laborantin ne peut plus saisir leur résultat. Il faut leur
créer leur facture manquante, **une seule fois**, juste après le `migrate` :

```bash
python manage.py facturer_actes_existants --dry-run
```

Cette première commande n'écrit **rien** : elle affiche seulement combien de
factures seraient créées. Si le compte te paraît juste, relance sans
`--dry-run` :

```bash
python manage.py facturer_actes_existants
```

Elle demande confirmation, puis liste chaque facture créée avec le montant à
encaisser. Les factures créées sont **non payées** : c'est à la réception de
les recouvrer. Les actes qui ont déjà une facture ne sont pas touchés, et les
rendez-vous **annulés** sont ignorés.

Ensuite seulement, **Reload** sur l'onglet *Web*.

> La commande est sans danger si tu la relances : elle ne crée jamais de
> doublon. Aux mises à jour suivantes, il n'y aura plus rien à régulariser
> (elle répondra « Rien à faire ») — les nouvelles factures sont créées
> automatiquement à l'enregistrement de chaque acte.
