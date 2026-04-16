"""
Drilling-time calculation engine.

This module is the Python-side replacement for the formula network in the
source workbook (sheets `A.Proposal`, `Tab 1.0`, `Tab 2.0`, `Tab 3.0`, `Chart`).

Rules implemented:

1. Each ProposalActivity / ProposalPhaseActivity contributes `effective_hours`
   (override or master default).
2. Per casing section:
     drilling_days      = Σ(hours of DRILLING activities)      / 24
     non_drilling_days  = Σ(hours of NON_DRILLING activities)  / 24
     completion_days    = Σ(hours of COMPLETION activities)    / 24
     total_days         = drilling + non_drilling + completion
     drilling_rate_m_per_day = interval_length_m / drilling_days  (safe division)
3. Per proposal:
     total_dryhole_days     = Σ total_days of sections where is_completion == False
     total_completion_days  = Σ total_days of sections where is_completion == True
     total_pre_spud_days    = Σ effective_hours of PRE_SPUD phase activities    / 24
     total_rig_release_days = Σ effective_hours of RIG_RELEASE phase activities / 24
     total_rig_days         = pre_spud + dryhole + completion + rig_release
         ↑ matches Excel `A.Proposal!F31`:
             =MAX(Chart!CA212:CA232) - MAX(Chart!BZ212:BZ232) + SUM(F29:J30)
           which decomposes to (pre_spud + rig_release) + (dryhole + completion).
           Sequential ops, NOT max — earlier comment about parallel ops was wrong.
           Note: mob/demob already counted inside Pre Spud activities; mob_days
           and demob_days fields on Proposal are kept for display/reference but
           NOT added to total_rig_days.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from masterdata.models import PhaseType


Q3 = Decimal("0.001")
Q2 = Decimal("0.01")


def _q(value, places=Q2):
    if value is None:
        return Decimal("0")
    return Decimal(value).quantize(places, rounding=ROUND_HALF_UP)


@dataclass
class SectionTotals:
    drilling_days: Decimal
    non_drilling_days: Decimal
    completion_days: Decimal
    total_days: Decimal
    drilling_rate_m_per_day: Decimal


@dataclass
class ProposalTotals:
    total_dryhole_days: Decimal
    total_completion_days: Decimal
    total_pre_spud_days: Decimal
    total_rig_release_days: Decimal
    total_rig_days: Decimal


def calculate_section_totals(section) -> SectionTotals:
    drilling_hours = Decimal("0")
    non_drilling_hours = Decimal("0")
    completion_hours = Decimal("0")

    for pa in section.activities.select_related("activity").all():
        hours = pa.effective_hours or Decimal("0")
        ptype = pa.activity.phase_type
        if ptype == PhaseType.DRILLING:
            drilling_hours += hours
        elif ptype == PhaseType.COMPLETION:
            completion_hours += hours
        else:
            non_drilling_hours += hours

    drilling_days = drilling_hours / Decimal("24")
    non_drilling_days = non_drilling_hours / Decimal("24")
    completion_days = completion_hours / Decimal("24")
    total_days = drilling_days + non_drilling_days + completion_days

    interval = section.interval_length_m
    if drilling_days > 0 and interval > 0:
        rate = interval / drilling_days
    else:
        rate = Decimal("0")

    return SectionTotals(
        drilling_days=_q(drilling_days, Q3),
        non_drilling_days=_q(non_drilling_days, Q3),
        completion_days=_q(completion_days, Q3),
        total_days=_q(total_days, Q3),
        drilling_rate_m_per_day=_q(rate, Q2),
    )


def recalculate_section(section, save: bool = True) -> SectionTotals:
    totals = calculate_section_totals(section)
    section.drilling_days = totals.drilling_days
    section.non_drilling_days = totals.non_drilling_days
    section.total_days = totals.total_days
    section.drilling_rate_m_per_day = totals.drilling_rate_m_per_day
    if save:
        section.save(update_fields=[
            "drilling_days", "non_drilling_days", "total_days",
            "drilling_rate_m_per_day",
        ])
    return totals


def _phase_days(proposal, phase) -> Decimal:
    """Sum effective_hours of all phase activities for a given phase, divided by 24."""
    from ..models import ProposalPhaseActivity  # local import to avoid circular

    total_hours = Decimal("0")
    qs = ProposalPhaseActivity.objects.filter(
        proposal=proposal, phase=phase
    ).select_related("activity")
    for pa in qs:
        total_hours += pa.effective_hours or Decimal("0")
    return total_hours / Decimal("24")


def calculate_proposal_totals(proposal) -> ProposalTotals:
    from ..models import ProposalPhase  # local import to avoid circular

    dryhole = Decimal("0")
    completion = Decimal("0")

    for section in proposal.casing_sections.all():
        if section.is_completion:
            completion += section.total_days
        else:
            dryhole += section.total_days

    pre_spud = _phase_days(proposal, ProposalPhase.PRE_SPUD)
    rig_release = _phase_days(proposal, ProposalPhase.RIG_RELEASE)

    rig_days = pre_spud + dryhole + completion + rig_release

    return ProposalTotals(
        total_dryhole_days=_q(dryhole, Q2),
        total_completion_days=_q(completion, Q2),
        total_pre_spud_days=_q(pre_spud, Q2),
        total_rig_release_days=_q(rig_release, Q2),
        total_rig_days=_q(rig_days, Q2),
    )


def recalculate_proposal(proposal, save: bool = True) -> ProposalTotals:
    # Refresh each section first so cached fields are current
    for section in proposal.casing_sections.all():
        recalculate_section(section)
    # Re-fetch to pick up fresh values
    proposal.refresh_from_db()
    totals = calculate_proposal_totals(proposal)
    proposal.total_dryhole_days = totals.total_dryhole_days
    proposal.total_completion_days = totals.total_completion_days
    proposal.total_pre_spud_days = totals.total_pre_spud_days
    proposal.total_rig_release_days = totals.total_rig_release_days
    proposal.total_rig_days = totals.total_rig_days
    if save:
        proposal.save(update_fields=[
            "total_dryhole_days", "total_completion_days",
            "total_pre_spud_days", "total_rig_release_days",
            "total_rig_days",
        ])
    return totals
