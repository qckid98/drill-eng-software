"""
Drilling-time calculation engine.

This module is the Python-side replacement for the formula network in the
source workbook (sheets `A.Proposal`, `Tab 1.0`, `Tab 2.0`, `Tab 3.0`, `Chart`).

Rules implemented:

1. Each ProposalActivity contributes `effective_hours` (override or master default).
2. Per casing section:
     drilling_days      = Σ(hours of DRILLING activities)      / 24
     non_drilling_days  = Σ(hours of NON_DRILLING activities)  / 24
     completion_days    = Σ(hours of COMPLETION activities)    / 24
     total_days         = drilling + non_drilling + completion
     drilling_rate_m_per_day = interval_length_m / drilling_days  (safe division)
3. Per proposal (follows Excel Tab 3.0 CUM. RIG DAYS — sequential sum):
     total_dryhole_days    = Σ total_days of sections where is_completion == False
     total_completion_days = Σ total_days of sections where is_completion == True
     total_rig_days        = Σ total_days of ALL sections + mob_days + demob_days
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
    section.completion_days = totals.completion_days
    section.total_days = totals.total_days
    section.drilling_rate_m_per_day = totals.drilling_rate_m_per_day
    if save:
        section.save(update_fields=[
            "drilling_days", "non_drilling_days", "completion_days",
            "total_days", "drilling_rate_m_per_day",
        ])
    return totals


def calculate_proposal_totals(proposal) -> ProposalTotals:
    dryhole = Decimal("0")
    completion = Decimal("0")
    sum_all_days = Decimal("0")

    for section in proposal.casing_sections.all():
        if section.is_completion:
            completion += section.total_days
        else:
            dryhole += section.total_days
        sum_all_days += section.total_days

    # Excel Tab 3.0 uses cumulative SUM for rig days (sequential operations)
    rig_days = (
        sum_all_days
        + Decimal(proposal.mob_days or 0)
        + Decimal(proposal.demob_days or 0)
    )

    return ProposalTotals(
        total_dryhole_days=_q(dryhole, Q2),
        total_completion_days=_q(completion, Q2),
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
    proposal.total_rig_days = totals.total_rig_days
    if save:
        proposal.save(update_fields=[
            "total_dryhole_days", "total_completion_days", "total_rig_days",
        ])
    # Auto-calculate overlap liner values on the Well
    update_overlap_liners(proposal)
    return totals


# ---------------------------------------------------------------------------
# Overlap liner auto-calculation
# ---------------------------------------------------------------------------
# In the Excel source (A.Proposal), overlap liner is calculated as:
#   Overlap Liner 7"   = depth of casing ABOVE the 7" liner − TOL of 7" liner
#   Overlap Liner 4½"  = depth of casing ABOVE the 4½" liner − TOL of 4½" liner
#
# Liner identification is by OD casing (od_csg):
#   7" liner  → od_csg ≈ 7.000
#   4½" liner → od_csg ≈ 4.500
# ---------------------------------------------------------------------------

_LINER_7_OD = Decimal("7")
_LINER_4_OD = Decimal("4.5")
_OD_TOLERANCE = Decimal("0.05")


def _find_liner_and_previous(sections, target_od):
    """Find a liner section by OD and return (liner_section, previous_section).

    ``sections`` must be ordered by ``order`` ascending.
    Returns (None, None) if no matching liner with a filled ``top_of_liner_m``
    is found.
    """
    for idx, sec in enumerate(sections):
        if sec.od_csg is None or sec.top_of_liner_m is None:
            continue
        if abs(sec.od_csg - target_od) <= _OD_TOLERANCE:
            prev = sections[idx - 1] if idx > 0 else None
            return sec, prev
    return None, None


def update_overlap_liners(proposal):
    """Recalculate overlap_liner_7in_m and overlap_liner_4in_m on the Well.

    Called automatically by ``recalculate_proposal``.
    """
    sections = list(
        proposal.casing_sections.order_by("order").only(
            "od_csg", "depth_m", "top_of_liner_m", "order",
        )
    )
    well = proposal.well
    changed = False

    # --- Overlap Liner 7" ---
    liner7, prev7 = _find_liner_and_previous(sections, _LINER_7_OD)
    if liner7 and prev7 and prev7.depth_m:
        overlap_7 = _q(prev7.depth_m - liner7.top_of_liner_m, Q2)
        if well.overlap_liner_7in_m != overlap_7:
            well.overlap_liner_7in_m = overlap_7
            changed = True
    elif well.overlap_liner_7in_m is not None:
        # No 7" liner found → clear the value
        well.overlap_liner_7in_m = None
        changed = True

    # --- Overlap Liner 4½" ---
    liner4, prev4 = _find_liner_and_previous(sections, _LINER_4_OD)
    if liner4 and prev4 and prev4.depth_m:
        overlap_4 = _q(prev4.depth_m - liner4.top_of_liner_m, Q2)
        if well.overlap_liner_4in_m != overlap_4:
            well.overlap_liner_4in_m = overlap_4
            changed = True
    elif well.overlap_liner_4in_m is not None:
        well.overlap_liner_4in_m = None
        changed = True

    if changed:
        well.save(update_fields=["overlap_liner_7in_m", "overlap_liner_4in_m"])
