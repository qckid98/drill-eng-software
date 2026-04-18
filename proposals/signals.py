"""
post_save/post_delete signals that keep cached totals up to date without
the caller having to remember to call the calculator manually.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import CasingSection, ProposalActivity, ProposalPhaseActivity
from .services.calc import recalculate_proposal, recalculate_section


@receiver([post_save, post_delete], sender=ProposalActivity)
def _activity_changed(sender, instance: ProposalActivity, **kwargs):
    section = instance.casing_section
    recalculate_section(section)
    recalculate_proposal(section.proposal)


@receiver([post_save, post_delete], sender=ProposalPhaseActivity)
def _phase_activity_changed(sender, instance: ProposalPhaseActivity, **kwargs):
    recalculate_proposal(instance.proposal)


@receiver([post_save, post_delete], sender=CasingSection)
def _section_changed(sender, instance: CasingSection, **kwargs):
    # Avoid infinite recursion: calc.recalculate_section saves via update_fields,
    # which still triggers post_save. Detect that case by checking update_fields.
    update_fields = kwargs.get("update_fields") or set()
    cached_only = {
        "drilling_days", "non_drilling_days", "completion_days",
        "total_days", "drilling_rate_m_per_day",
    }
    if update_fields and set(update_fields).issubset(cached_only):
        return
    recalculate_proposal(instance.proposal)
