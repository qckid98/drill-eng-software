"""
Helpers for applying section templates (preset activity lists)
to casing sections.
"""

from proposals.models import ProposalActivity
from proposals.services.calc import recalculate_proposal


def apply_template_to_section(section, template, replace=False):
    """Bulk-create ProposalActivity rows from SectionTemplate.items.

    Args:
        section: CasingSection instance
        template: SectionTemplate instance
        replace: if True, delete existing activities first
    """
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
