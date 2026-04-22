"""
AFE calculation engine.

Replicates the F.CONT SUMIFS roll-ups and the formulas that feed the 58
static AFE lines from sheet `AFE_v.2017_Kontrak JTB_Update April 2026.xlsx`.

Flow: DrillTime Proposal -> AFE
  1. Proposal provides "drivers": rig_days, dhb_days, cb_days, max_depth, casing weight
  2. Each AFETemplate line uses a calc_method to compute cost from drivers + rate card
  3. AFELineComponent records store the detail breakdown (from E.COMP)
  4. Totals are rolled up into tangible/intangible/grand total
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models.signals import post_save

from proposals.models import CasingSection, Proposal

from ..models import (
    AFE,
    AFECategory,
    AFELine,
    AFELineComponent,
    AFETemplate,
    CalcMethod,
    PhaseFlag,
    RateCardItem,
)

Q2 = Decimal("0.01")
Q0 = Decimal("1")
METERS_TO_FEET = Decimal("3.2808")


# ---------------------------------------------------------------------------
# Proposal drivers -- the numeric inputs from DrillTime that feed AFE calcs
# ---------------------------------------------------------------------------
@dataclass
class ProposalDrivers:
    rig_days: Decimal
    dhb_days: Decimal
    cb_days: Decimal
    mob_days: Decimal
    max_depth_m: Decimal
    total_casing_weight_lbs: Decimal
    exchange_rate: Decimal

    @classmethod
    def from_proposal(cls, proposal: Proposal) -> "ProposalDrivers":
        sections = list(CasingSection.objects
                        .filter(proposal=proposal)
                        .order_by("order"))
        # These come directly from DrillTime calculation (SUM-based)
        rig_days = proposal.total_rig_days or Decimal("0")
        dhb_days = proposal.total_dryhole_days or Decimal("0")
        cb_days = proposal.total_completion_days or Decimal("0")
        mob_days = (proposal.mob_days or Decimal("0")) + (proposal.demob_days or Decimal("0"))
        max_depth = max((s.depth_m or Decimal("0") for s in sections),
                        default=Decimal("0"))

        total_weight = Decimal("0")
        prev_depth = Decimal("0")
        for s in sections:
            depth = s.depth_m or Decimal("0")
            interval_m = max(depth - prev_depth, Decimal("0"))
            interval_ft = interval_m * METERS_TO_FEET
            weight_per_ft = s.weight_lbs_ft or Decimal("0")
            total_weight += interval_ft * weight_per_ft
            prev_depth = depth

        return cls(
            rig_days=Decimal(rig_days),
            dhb_days=Decimal(dhb_days),
            cb_days=Decimal(cb_days),
            mob_days=Decimal(mob_days),
            max_depth_m=Decimal(max_depth),
            total_casing_weight_lbs=total_weight.quantize(Q2, rounding=ROUND_HALF_UP),
            exchange_rate=proposal.dollar_rate or Decimal("16500"),
        )


# ---------------------------------------------------------------------------
# Rate card lookup helpers
# ---------------------------------------------------------------------------
def _pick_rate(template: AFETemplate, phase: PhaseFlag | None = None) -> RateCardItem | None:
    qs = RateCardItem.objects.filter(afe_line=template)
    if phase:
        hit = qs.filter(phase_flag=phase).order_by("-unit_price_usd").first()
        if hit:
            return hit
    return qs.order_by("-unit_price_usd").first()


def _get_all_rates(template: AFETemplate) -> list[RateCardItem]:
    """Get all rate card items linked to this template."""
    return list(RateCardItem.objects.filter(afe_line=template).order_by("code"))


# ---------------------------------------------------------------------------
# Per-template calculators
# ---------------------------------------------------------------------------
def _calc_line_amount(template: AFETemplate, drivers: ProposalDrivers) -> tuple[Decimal, Decimal | None, Decimal | None, RateCardItem | None]:
    """Return (calculated_usd, quantity, unit_price_usd, rate_item)."""
    method = template.calc_method

    if method == CalcMethod.RIG_DAYS_RATE:
        rate = _pick_rate(template)
        price = rate.unit_price_usd if rate else Decimal("0")
        amount = drivers.rig_days * price
        return amount.quantize(Q2, rounding=ROUND_HALF_UP), drivers.rig_days, price, rate

    if method == CalcMethod.DHB_CB_SPLIT:
        dhb_rate = _pick_rate(template, PhaseFlag.DHB)
        cb_rate = _pick_rate(template, PhaseFlag.CB)
        fallback = _pick_rate(template)
        dhb_price = (dhb_rate or fallback).unit_price_usd if (dhb_rate or fallback) else Decimal("0")
        cb_price = (cb_rate or fallback).unit_price_usd if (cb_rate or fallback) else Decimal("0")
        amount = (drivers.dhb_days * dhb_price) + (drivers.cb_days * cb_price)
        qty = drivers.dhb_days + drivers.cb_days
        chosen = dhb_rate or cb_rate or fallback
        blended = ((dhb_price + cb_price) / 2) if (dhb_price or cb_price) else Decimal("0")
        return amount.quantize(Q2, rounding=ROUND_HALF_UP), qty, blended.quantize(Q2), chosen

    if method == CalcMethod.PER_METER_DEPTH:
        rate = _pick_rate(template)
        price = rate.unit_price_usd if rate else Decimal("0")
        amount = drivers.max_depth_m * price
        return amount.quantize(Q2, rounding=ROUND_HALF_UP), drivers.max_depth_m, price, rate

    if method == CalcMethod.PER_CASING_WEIGHT:
        rate = _pick_rate(template)
        price = rate.unit_price_usd if rate else Decimal("0")
        amount = drivers.total_casing_weight_lbs * price
        return amount.quantize(Q2, rounding=ROUND_HALF_UP), drivers.total_casing_weight_lbs, price, rate

    if method == CalcMethod.LUMP_SUM:
        rate = _pick_rate(template)
        price = rate.unit_price_usd if rate else Decimal("0")
        return price.quantize(Q2, rounding=ROUND_HALF_UP), Decimal("1"), price, rate

    # MANUAL or subtotal rows
    return Decimal("0"), None, None, None


# ---------------------------------------------------------------------------
# Component generation -- populate AFELineComponent from rate cards
# ---------------------------------------------------------------------------
def _generate_components(afe_line: AFELine, drivers: ProposalDrivers) -> None:
    """Create AFELineComponent records from all rate card items linked to this template."""
    # Clear existing components
    afe_line.components.all().delete()

    rates = _get_all_rates(afe_line.template)
    if not rates:
        return

    for idx, rate in enumerate(rates):
        qty = Decimal("1")
        method = afe_line.template.calc_method

        # Determine quantity based on calc method
        if method == CalcMethod.RIG_DAYS_RATE:
            qty = drivers.rig_days
        elif method == CalcMethod.DHB_CB_SPLIT:
            if rate.phase_flag == PhaseFlag.DHB:
                qty = drivers.dhb_days
            elif rate.phase_flag == PhaseFlag.CB:
                qty = drivers.cb_days
            else:
                qty = drivers.rig_days
        elif method == CalcMethod.PER_METER_DEPTH:
            qty = drivers.max_depth_m

        total = (qty * rate.unit_price_usd).quantize(Q2, rounding=ROUND_HALF_UP)

        AFELineComponent.objects.create(
            afe_line=afe_line,
            description=rate.description[:300],
            quantity=qty,
            unit_of_measure=rate.unit_of_measure,
            unit_price_usd=rate.unit_price_usd,
            total_usd=total,
            material_type=rate.material_type,
            material_category="",
            stock_status="",
            phase_flag=rate.phase_flag,
            order=idx,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
@transaction.atomic
def generate_afe_from_proposal(afe: AFE, *, overwrite: bool = True) -> None:
    """Populate AFELine rows for every AFETemplate based on the proposal.

    Also generates AFELineComponent detail records from rate cards.
    If `overwrite=True`, existing override_usd values are wiped.

    Temporarily disconnects the AFELine post_save signal to avoid
    calling recalculate_afe() 58 times — it is called once at the end.
    """
    from ..signals import _afeline_saved

    # Disconnect signal to avoid 58x recalculate during bulk line creation
    post_save.disconnect(_afeline_saved, sender=AFELine)
    try:
        drivers = ProposalDrivers.from_proposal(afe.proposal)
        templates = list(AFETemplate.objects.all().order_by("order", "line_code"))

        for tpl in templates:
            if tpl.is_subtotal_row:
                AFELine.objects.update_or_create(
                    afe=afe, template=tpl,
                    defaults={
                        "calculated_usd": Decimal("0"),
                        "override_usd": None,
                        "quantity": None,
                        "unit_price_usd": None,
                        "rate_card_item": None,
                    },
                )
                continue

            amount, qty, unit_price, rate_item = _calc_line_amount(tpl, drivers)
            defaults = {
                "calculated_usd": amount,
                "quantity": qty,
                "unit_price_usd": unit_price,
                "rate_card_item": rate_item,
            }
            if overwrite:
                defaults["override_usd"] = None

            line, _ = AFELine.objects.update_or_create(
                afe=afe, template=tpl, defaults=defaults
            )

            # Generate component detail for this line
            if overwrite:
                _generate_components(line, drivers)
    finally:
        # Always reconnect the signal, even if an error occurred
        post_save.connect(_afeline_saved, sender=AFELine)

    recalculate_afe(afe)


@transaction.atomic
def recalculate_afe(afe: AFE) -> AFE:
    """Re-sum tangible/intangible totals and derived KPIs."""
    tangible = Decimal("0")
    intangible = Decimal("0")
    for line in afe.lines.select_related("template").all():
        if line.template.is_subtotal_row:
            continue
        amount = line.final_usd
        if line.template.category == AFECategory.TANGIBLE:
            tangible += amount
        else:
            intangible += amount

    base = tangible + intangible
    contingency_pct = afe.contingency_percent or Decimal("0")
    contingency_amount = (base * contingency_pct / Decimal("100")).quantize(Q2, rounding=ROUND_HALF_UP)
    grand_total = base + contingency_amount

    # Cost per meter / day (rough KPIs from DrillTime data)
    drivers = ProposalDrivers.from_proposal(afe.proposal)
    cost_per_meter = (grand_total / drivers.max_depth_m).quantize(Q2, rounding=ROUND_HALF_UP) \
        if drivers.max_depth_m else Decimal("0")
    cost_per_day = (grand_total / drivers.rig_days).quantize(Q2, rounding=ROUND_HALF_UP) \
        if drivers.rig_days else Decimal("0")

    afe.total_tangible_usd = tangible.quantize(Q2, rounding=ROUND_HALF_UP)
    afe.total_intangible_usd = intangible.quantize(Q2, rounding=ROUND_HALF_UP)
    afe.contingency_amount_usd = contingency_amount
    afe.grand_total_usd = grand_total.quantize(Q2, rounding=ROUND_HALF_UP)
    afe.cost_per_meter_usd = cost_per_meter
    afe.cost_per_day_usd = cost_per_day
    afe.save(update_fields=[
        "total_tangible_usd",
        "total_intangible_usd",
        "contingency_amount_usd",
        "grand_total_usd",
        "cost_per_meter_usd",
        "cost_per_day_usd",
    ])
    return afe
