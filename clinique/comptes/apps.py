from django.apps import AppConfig


class ComptesConfig(AppConfig):
    name = 'comptes'

    def ready(self):
        # Enregistre les recherches __mots et __lower dès le démarrage, et pas
        # seulement quand une vue importe le module (commandes, modèles…).
        from . import recherche  # noqa: F401
