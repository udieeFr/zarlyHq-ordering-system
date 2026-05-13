from django.apps import AppConfig


class AdminsConfig(AppConfig):
    name = 'admins'

    def ready(self):
        import admins.signals  # noqa: F401
