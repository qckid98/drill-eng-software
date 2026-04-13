"""
Signal handlers: keep AFE cached totals in sync with AFELine writes.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import AFE, AFELine

# Fields that the recalc routine itself writes back on the AFE — ignore those
# to avoid recursion when we save totals.
_CACHE_FIELDS = {
    "total_tangible_usd",
    "total_intangible_usd",
    "contingency_amount_usd",
    "grand_total_usd",
    "cost_per_meter_usd",
    "cost_per_day_usd",
}


@receiver(post_save, sender=AFELine)
def _afeline_saved(sender, instance: AFELine, **kwargs):
    from .services.calc import recalculate_afe
    recalculate_afe(instance.afe)


@receiver(post_delete, sender=AFELine)
def _afeline_deleted(sender, instance: AFELine, **kwargs):
    from .services.calc import recalculate_afe
    try:
        recalculate_afe(instance.afe)
    except AFE.DoesNotExist:
        pass


@receiver(post_save, sender=AFE)
def _afe_saved(sender, instance: AFE, created, update_fields, **kwargs):
    if created:
        return
    if update_fields and set(update_fields).issubset(_CACHE_FIELDS):
        return  # cache-only save; skip
    # other edits (e.g. contingency percent) also require recalculation
    from .services.calc import recalculate_afe
    recalculate_afe(instance)
