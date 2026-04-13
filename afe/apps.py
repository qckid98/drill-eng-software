from django.apps import AppConfig


class AfeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "afe"
    verbose_name = "AFE (Authorization For Expenditure)"

    def ready(self):
        # Register post_save signals for AFELine → recalc totals
        from . import signals  # noqa: F401
