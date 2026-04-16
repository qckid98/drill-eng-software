"""
Helpers for applying section templates (preset variants from Tab 2.0 Excel)
to casing sections or proposal-level phases.
"""

from proposals.models import ProposalActivity, ProposalPhaseActivity
from proposals.services.calc import recalculate_proposal


def apply_template_to_section(section, template, replace=False):
    """Bulk-create ProposalActivity rows from SectionTemplate.items."""
    if replace:
        section.activities.all().delete()

    for idx, item in enumerate(template.items.select_related("activity").all()):
        ProposalActivity.objects.create(
            casing_section=section,
            activity=item.activity,
            order=idx,
            hours_override=item.default_hours,
        )

    recalculate_proposal(section.proposal)


def apply_template_to_phase(proposal, phase, template, replace=False):
    """Bulk-create ProposalPhaseActivity rows from SectionTemplate.items."""
    if replace:
        proposal.phase_activities.filter(phase=phase).delete()

    for idx, item in enumerate(template.items.select_related("activity").all()):
        ProposalPhaseActivity.objects.create(
            proposal=proposal,
            phase=phase,
            activity=item.activity,
            order=idx,
            hours_override=item.default_hours,
        )

    recalculate_proposal(proposal)
