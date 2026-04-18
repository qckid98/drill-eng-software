"""
AFE (Authorization For Expenditure) data model.

Replicates the structure of `F.CONT` sheet in
`AFE_v.2017_Kontrak JTB_Update April 2026.xlsx`:

- 58 static lines grouped into Tangible / Intangible, split further into
  subsections (Preparation, Drilling, Formation, Completion, General).
- Each AFE document is tied to an approved Proposal and holds 58
  AFELine rows (one per template).
- Rate card items come from sheet `D.MATE` and are linked to the template
  they typically feed; engineers can override calculated values per line.
"""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from proposals.models import Proposal


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class AFECategory(models.TextChoices):
    TANGIBLE = "TANGIBLE", "Tangible"
    INTANGIBLE = "INTANGIBLE", "Intangible"


class CalcMethod(models.TextChoices):
    RIG_DAYS_RATE = "RIG_DAYS_RATE", "Rig days × daily rate"
    DHB_CB_SPLIT = "DHB_CB_SPLIT", "DHB days × rate + CB days × rate"
    PER_METER_DEPTH = "PER_METER_DEPTH", "Max depth × rate per meter"
    PER_CASING_WEIGHT = "PER_CASING_WEIGHT", "Σ casing weight × rate/lb"
    LUMP_SUM = "LUMP_SUM", "Flat lump sum"
    MANUAL = "MANUAL", "Manual input"


class AFESection(models.TextChoices):
    TANGIBLE = "TANGIBLE", "Tangible Cost"
    PREPARATION = "PREPARATION", "Preparation & Termination"
    DRILLING = "DRILLING", "Drilling / Workover"
    FORMATION = "FORMATION", "Formation Evaluation"
    COMPLETION = "COMPLETION", "Completion"
    GENERAL = "GENERAL", "General / Overhead"


class PhaseFlag(models.TextChoices):
    DHB = "DHB", "Dry Hole Based"
    CB = "CB", "Completion Based"
    BOTH = "BOTH", "Both"


class AFEStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    REVISION = "REVISION", "Needs Revision"


# ---------------------------------------------------------------------------
# Master tables
# ---------------------------------------------------------------------------
class AFETemplate(models.Model):
    """One of the 58 lines in the F.CONT AFE form (static catalog)."""

    line_code = models.CharField(max_length=8, unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=AFECategory.choices)
    section = models.CharField(max_length=20, choices=AFESection.choices)
    calc_method = models.CharField(max_length=30, choices=CalcMethod.choices,
                                    default=CalcMethod.MANUAL)
    is_subtotal_row = models.BooleanField(default=False,
        help_text="Subtotal / header rows aren't filled by engineer.")
    order = models.PositiveIntegerField(default=0)
    default_rate_code = models.CharField(
        max_length=20, blank=True,
        help_text="Optional hint for picking default RateCardItem code.",
    )
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["order", "line_code"]

    def __str__(self) -> str:
        return f"{self.line_code} — {self.name}"


class RateCardItem(models.Model):
    """Unit price entry imported from sheet `D.MATE` (with versioning)."""

    code = models.CharField(max_length=30, db_index=True)
    description = models.CharField(max_length=300)
    unit_of_measure = models.CharField(max_length=30, blank=True)
    unit_price_usd = models.DecimalField(max_digits=14, decimal_places=2,
                                          default=Decimal("0"))
    afe_line = models.ForeignKey(
        AFETemplate, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="rate_items",
        help_text="Which AFE line this rate feeds by default.",
    )
    phase_flag = models.CharField(max_length=5, choices=PhaseFlag.choices,
                                   default=PhaseFlag.BOTH)
    material_type = models.CharField(max_length=30, blank=True)
    source_sheet = models.CharField(max_length=30, blank=True, default="D.MATE")
    effective_from = models.DateField(default=timezone.localdate)
    effective_to = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["afe_line__order", "code"]
        indexes = [
            models.Index(fields=["afe_line", "phase_flag"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.description[:40]} (${self.unit_price_usd})"


class RateCardImportLog(models.Model):
    """Audit trail of D.MATE re-uploads."""

    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                    on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_name = models.CharField(max_length=255)
    items_created = models.PositiveIntegerField(default=0)
    items_updated = models.PositiveIntegerField(default=0)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]


# ---------------------------------------------------------------------------
# AFE document
# ---------------------------------------------------------------------------
class AFE(models.Model):
    """An AFE revision generated from one approved Proposal."""

    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE,
                                  related_name="afes")
    version = models.PositiveIntegerField(default=1)
    doc_number = models.CharField(max_length=80, unique=True, blank=True)
    title = models.CharField(max_length=200, blank=True)

    status = models.CharField(max_length=20, choices=AFEStatus.choices,
                               default=AFEStatus.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                    on_delete=models.PROTECT,
                                    related_name="afes_created")

    contingency_percent = models.DecimalField(max_digits=5, decimal_places=2,
                                                default=Decimal("0"))
    exchange_rate_override = models.DecimalField(max_digits=14, decimal_places=4,
                                                   null=True, blank=True,
        help_text="USD→IDR rate. Kalau kosong pakai proposal.dollar_rate.")

    # Cached totals — updated by services.calc.recalculate_afe()
    total_tangible_usd = models.DecimalField(max_digits=16, decimal_places=2,
                                               default=Decimal("0"))
    total_intangible_usd = models.DecimalField(max_digits=16, decimal_places=2,
                                                 default=Decimal("0"))
    contingency_amount_usd = models.DecimalField(max_digits=16, decimal_places=2,
                                                   default=Decimal("0"))
    grand_total_usd = models.DecimalField(max_digits=16, decimal_places=2,
                                            default=Decimal("0"))
    cost_per_meter_usd = models.DecimalField(max_digits=14, decimal_places=2,
                                               default=Decimal("0"))
    cost_per_day_usd = models.DecimalField(max_digits=14, decimal_places=2,
                                             default=Decimal("0"))

    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("proposal", "version")]

    def __str__(self) -> str:
        return self.doc_number or f"AFE draft #{self.pk}"

    # --- helpers --------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.pk:
            # Auto-compute version = max existing version + 1 for this proposal.
            # Views may also pass version explicitly; writing the same value
            # back is idempotent.
            prev = (AFE.objects
                    .filter(proposal=self.proposal)
                    .order_by("-version")
                    .first())
            next_version = (prev.version + 1) if prev else 1
            if not self.version or self.version < next_version:
                self.version = next_version
        if not self.doc_number:
            self.doc_number = f"DEP/Form/AFE/{self.proposal_id or 'X'}/v{self.version}"
        super().save(*args, **kwargs)

    @property
    def effective_exchange_rate(self) -> Decimal:
        if self.exchange_rate_override:
            return self.exchange_rate_override
        return self.proposal.dollar_rate or Decimal("16500")

    @property
    def grand_total_idr(self) -> Decimal:
        return (self.grand_total_usd or Decimal("0")) * self.effective_exchange_rate

    # --- role permissions ----------------------------------------------
    def can_edit(self, user) -> bool:
        if user.is_superuser or getattr(user, "is_admin_role", False):
            return True
        if self.status not in (AFEStatus.DRAFT, AFEStatus.REVISION):
            return False
        return user == self.created_by

    def can_submit(self, user) -> bool:
        return self.can_edit(user) and self.status in (
            AFEStatus.DRAFT, AFEStatus.REVISION,
        )

    def can_review(self, user) -> bool:
        return getattr(user, "is_supervisor", False) and self.status == AFEStatus.SUBMITTED

    def can_approve(self, user) -> bool:
        return getattr(user, "is_management", False) and self.status == AFEStatus.UNDER_REVIEW


class AFELine(models.Model):
    """One of the 58 F.CONT rows for a specific AFE instance."""

    afe = models.ForeignKey(AFE, on_delete=models.CASCADE, related_name="lines")
    template = models.ForeignKey(AFETemplate, on_delete=models.PROTECT,
                                  related_name="+")
    rate_card_item = models.ForeignKey(RateCardItem, null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name="+")

    quantity = models.DecimalField(max_digits=14, decimal_places=3,
                                     null=True, blank=True)
    unit_price_usd = models.DecimalField(max_digits=14, decimal_places=2,
                                          null=True, blank=True,
        help_text="Snapshot dari rate card saat AFE dibuat.")
    calculated_usd = models.DecimalField(max_digits=16, decimal_places=2,
                                           default=Decimal("0"))
    override_usd = models.DecimalField(max_digits=16, decimal_places=2,
                                         null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["template__order", "template__line_code"]
        unique_together = [("afe", "template")]

    def __str__(self) -> str:
        return f"{self.afe.doc_number} · line {self.template.line_code}"

    @property
    def final_usd(self) -> Decimal:
        if self.override_usd is not None:
            return self.override_usd
        return self.calculated_usd or Decimal("0")


class AFELineComponent(models.Model):
    """Detail component under an AFE line — maps to E.COMP rows in the Excel.

    Example: AFE line "CASING" (line_code=2) has components:
      - 30" CSG STOVE, 6 MTR, 12 MM  qty=9  price=$2200
      - 20" CSG ERW, K-55, 94#, BTC  qty=53 price=$6114
      - etc.
    """

    afe_line = models.ForeignKey(
        AFELine, on_delete=models.CASCADE, related_name="components"
    )
    description = models.CharField(max_length=300)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit_of_measure = models.CharField(max_length=30, blank=True)
    unit_price_usd = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_usd = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    material_type = models.CharField(
        max_length=30, blank=True,
        help_text="MATERIAL or NON MATERIAL",
    )
    material_category = models.CharField(
        max_length=60, blank=True,
        help_text="SKK MIGAS category, e.g. Drive pipe, Conductor casing",
    )
    stock_status = models.CharField(
        max_length=20, blank=True,
        help_text="STOCK or NEW",
    )
    phase_flag = models.CharField(
        max_length=5, choices=PhaseFlag.choices, default=PhaseFlag.BOTH,
        help_text="DHB, CB, or BOTH",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["afe_line_id", "order"]

    def __str__(self) -> str:
        return f"{self.description[:50]} (qty={self.quantity})"

    def save(self, *args, **kwargs):
        # Auto-calculate total
        self.total_usd = (self.quantity or Decimal("0")) * (self.unit_price_usd or Decimal("0"))
        super().save(*args, **kwargs)


class AFEApprovalLog(models.Model):
    afe = models.ForeignKey(AFE, on_delete=models.CASCADE,
                             related_name="approval_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,
                               on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=30)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    comment = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.afe} {self.action} by {self.actor}"

    def get_action_display(self):
        return {
            "submit": "Submit",
            "forward": "Forward",
            "approve": "Approve",
            "reject": "Reject",
            "request_revision": "Request Revision",
        }.get(self.action, self.action)
