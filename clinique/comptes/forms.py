"""Formulaire de la page « Mot de passe oublié »."""
import unicodedata

from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User


def _replier(texte):
    """Forme de comparaison recommandée par Unicode, la même que celle de Django."""
    return unicodedata.normalize('NFKC', texte).casefold()


class MotDePasseOublieForm(PasswordResetForm):
    """Retrouve le compte quelle que soit la façon dont l'adresse est tapée."""

    def get_users(self, email):
        # Django cherche avec __iexact, que notre base MySQL en utf8mb4_bin rend
        # sensible à la casse : « Aminata@exemple.ml » ne trouvait pas
        # « aminata@exemple.ml », et la page affichait quand même sa confirmation.
        # Le reste est la règle de Django : compte actif, mot de passe utilisable,
        # et l'email part à l'adresse ENREGISTRÉE, jamais à celle qui a été tapée.
        comptes = User.objects.filter(email__lower=email.lower(), is_active=True)
        return (
            u for u in comptes
            if u.has_usable_password() and _replier(email) == _replier(u.email)
        )
