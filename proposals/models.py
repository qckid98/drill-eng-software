"""
Core proposal models — replace the Excel sheets `A.Proposal`, `Tab 2.0`,
and the aggregated output of `Tab 3.0`.

Calculation logic is deliberately kept OUT of this file and lives in
`proposals/services/calc.py`. Models only store raw inputs plus cached
totals that the calculator refreshes via post_save signals.
"""

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.urls import reverse

from masterdata.models import (
    DrillingActivity,
    HoleSection,
    MudType,
    RigSpec,
)
from wells.models import Well


class ProposalStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted (awaiting supervisor)"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review (management)"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    REVISION = "REVISION", "Revision requested"
    TEMPLATE = "TEMPLATE", "Template"


class Proposal(models.Model):
    # ---------------- identity ----------------
    doc_number = models.CharField(max_length=60, unique=True, blank=True)
    version = models.CharField(max_length=20, default="2.4/2017")
    title = models.CharField(max_length=200, blank=True)

    # ---------------- relationships ----------------
    well = models.ForeignKey(Well, on_delete=models.PROTECT, related_name="proposals")
    rig = models.ForeignKey(
        RigSpec, on_delete=models.PROTECT, related_name="proposals",
        null=True, blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="proposals_created",
    )

    # ---------------- dates & scheduling ----------------
    date_input = models.DateField(
        null=True, blank=True,
        help_text="Tanggal input proposal (DD-MMM-YYYY dari A.Proposal row 9)",
    )
    spud_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)
    mob_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    demob_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    dollar_rate = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="USD/IDR exchange rate at time of proposal",
    )

    # ---------------- workflow ----------------
    status = models.CharField(
        max_length=20, choices=ProposalStatus.choices, default=ProposalStatus.DRAFT
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    # ---------------- cached totals (refreshed by calc.py) ----------------
    total_dryhole_days = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_completion_days = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_rig_days = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.doc_number or 'DRAFT'} — {self.well}"

    def save(self, *args, **kwargs):
        if not self.doc_number:
            # Auto-assign doc number after first save (needs PK)
            super().save(*args, **kwargs)
            from django.conf import settings as s
            self.doc_number = f"{s.DRILLTIME_DOC_PREFIX}/{self.pk:05d}"
            kwargs2 = {"update_fields": ["doc_number"]}
            super().save(**kwargs2)
            return
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("proposals:detail", args=[self.pk])

    # ---- workflow predicates ----
    def can_edit(self, user) -> bool:
        if self.status not in (ProposalStatus.DRAFT, ProposalStatus.REVISION):
            return False
        return user == self.created_by or user.is_admin_role

    def can_submit(self, user) -> bool:
        return self.can_edit(user) and self.casing_sections.exists()

    def can_review(self, user) -> bool:
        return self.status == ProposalStatus.SUBMITTED and user.is_supervisor

    def can_approve(self, user) -> bool:
        return self.status == ProposalStatus.UNDER_REVIEW and user.is_management

    @property
    def is_template(self) -> bool:
        return self.status == ProposalStatus.TEMPLATE

    def clone_from_template(self, user, well):
        """Create a new DRAFT proposal by cloning this template."""
        if not self.is_template:
            raise ValueError("Can only clone from a TEMPLATE proposal.")
        new_proposal = Proposal.objects.create(
            well=well,
            rig=self.rig,
            created_by=user,
            version=self.version,
            title=f"Copy of {self.title}",
            mob_days=self.mob_days,
            demob_days=self.demob_days,
            status=ProposalStatus.DRAFT,
        )
        # Clone casing sections and their activities
        for section in self.casing_sections.all():
            old_section_pk = section.pk
            section.pk = None
            section.proposal = new_proposal
            section.save()
            # Clone activities for this section
            from proposals.models import ProposalActivity
            old_activities = ProposalActivity.objects.filter(
                casing_section_id=old_section_pk
            ).select_related("activity")
            for act in old_activities:
                act.pk = None
                act.casing_section = section
                act.save()
        # Clone tubing items
        for tubing in self.tubing_items.all():
            tubing.pk = None
            tubing.proposal = new_proposal
            tubing.save()
        # Clone operational rates
        for rate in self.operational_rates.all():
            rate.pk = None
            rate.proposal = new_proposal
            rate.save()
        return new_proposal


class CasingSection(models.Model):
    """A single row in the casing design table (Section 3 of A.Proposal)."""

    proposal = models.ForeignKey(
        Proposal, on_delete=models.CASCADE, related_name="casing_sections"
    )
    order = models.PositiveIntegerField(default=0)
    hole_section = models.ForeignKey(
        HoleSection, on_delete=models.PROTECT, related_name="+",
    )
    od_csg = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    id_csg = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    weight_lbs_ft = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    depth_m = models.DecimalField(max_digits=10, decimal_places=2)
    top_of_liner_m = models.DecimalField(
        "TOL (mMD)", max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Top of Liner (mMD). Isi hanya untuk liner, kosongkan untuk casing penuh.",
    )
    mud_type = models.ForeignKey(
        MudType, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_completion = models.BooleanField(
        default=False,
        help_text="Check if this row represents the completion phase (not dry hole).",
    )
    notes = models.CharField(max_length=255, blank=True)

    # --- Casing properties (from A.Proposal blue cells rows 36-43) ---
    sg_from = models.DecimalField(
        "SG From", max_digits=6, decimal_places=3, null=True, blank=True,
        help_text="Mud specific gravity lower bound",
    )
    sg_to = models.DecimalField(
        "SG To", max_digits=6, decimal_places=3, null=True, blank=True,
        help_text="Mud specific gravity upper bound",
    )
    casing_type = models.CharField(
        max_length=30, blank=True,
        help_text="Casing grade, e.g. K-55, N-80",
    )
    pounder = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Casing weight (lbs/ft) — pounder column",
    )
    thread = models.CharField(
        max_length=30, blank=True,
        help_text="Thread type, e.g. BTC, LTC, STC",
    )
    range_spec = models.CharField(
        max_length=20, blank=True,
        help_text="Casing range, e.g. R-1, R-2, R-3",
    )
    casing_title = models.CharField(
        max_length=255, blank=True,
        help_text="Auto-generated casing summary, e.g. 13 3/8'' Csg, K-55, 54.5 ppf, BTC, R-3 at 734 mMD",
    )

    # --- Section type (from Tab 2.0 grouping) ---
    section_type = models.CharField(
        max_length=200, blank=True,
        help_text="Drilling section type from Tab 2.0, e.g. PRESPUD PREPARATION W/ ENDURANCE TEST",
    )

    # cached totals (refreshed by calc.py whenever activities change)
    drilling_days = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    non_drilling_days = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    completion_days = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    total_days = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    drilling_rate_m_per_day = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    class Meta:
        ordering = ["proposal_id", "order"]

    def __str__(self):
        return f"{self.hole_section} @ {self.depth_m} m"

    def build_casing_title(self):
        """Auto-generate casing title from component fields."""
        parts = [f"{self.od_csg}'' Csg" if self.od_csg else ""]
        if self.casing_type:
            parts.append(self.casing_type)
        if self.weight_lbs_ft:
            parts.append(f"{self.weight_lbs_ft} ppf")
        if self.thread:
            parts.append(self.thread)
        if self.range_spec:
            parts.append(self.range_spec)
        if self.depth_m:
            parts.append(f"at {self.depth_m} mMD")
        return ", ".join(p for p in parts if p)

    @property
    def previous_depth(self) -> Decimal:
        prev = (
            CasingSection.objects
            .filter(proposal=self.proposal, order__lt=self.order)
            .order_by("-order")
            .first()
        )
        return prev.depth_m if prev else Decimal("0")

    @property
    def interval_length_m(self) -> Decimal:
        return max(Decimal("0"), self.depth_m - self.previous_depth)


class ProposalActivity(models.Model):
    """
    An activity picked from the master library and assigned to a casing
    section. Replaces a row from the Excel Tab 2.0 sheet.
    """

    casing_section = models.ForeignKey(
        CasingSection, on_delete=models.CASCADE, related_name="activities"
    )
    activity = models.ForeignKey(
        DrillingActivity, on_delete=models.PROTECT, related_name="+"
    )
    order = models.PositiveIntegerField(default=0)
    hours_override = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Leave blank to use the default hours from the master activity.",
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["casing_section_id", "order"]

    def __str__(self):
        return f"{self.casing_section} — {self.activity}"

    @property
    def effective_hours(self) -> Decimal:
        if self.hours_override is not None:
            return self.hours_override
        return self.activity.default_hours

    @property
    def effective_days(self) -> Decimal:
        return (self.effective_hours / Decimal("24")).quantize(Decimal("0.001"))


class TubingItem(models.Model):
    """Production string tubing specification (Section 4 of A.Proposal).
    Multiple rows per proposal (Excel has 3.5", 2.875", 2.375")."""

    proposal = models.ForeignKey(
        Proposal, on_delete=models.CASCADE, related_name="tubing_items"
    )
    order = models.PositiveIntegerField(default=0)
    od_inch = models.DecimalField(
        "OD (inch)", max_digits=6, decimal_places=3, null=True, blank=True
    )
    id_inch = models.DecimalField(
        "ID (inch)", max_digits=6, decimal_places=3, null=True, blank=True
    )
    weight_lbs_ft = models.DecimalField(
        "Weight (lbs/ft)", max_digits=6, decimal_places=2, null=True, blank=True
    )
    avg_length_m = models.DecimalField(
        "Avg length (m)", max_digits=6, decimal_places=2, null=True, blank=True
    )
    depth_md = models.DecimalField(
        "Depth MD (m)", max_digits=10, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["proposal_id", "order"]

    def __str__(self):
        return f"Tubing {self.od_inch}\" @ {self.depth_md} m"


class FormationMarker(models.Model):
    """Formation marker entries for a proposal."""

    proposal = models.ForeignKey(
        Proposal, on_delete=models.CASCADE, related_name="formation_markers"
    )
    order = models.PositiveIntegerField(default=0)
    name = models.CharField(max_length=120, help_text="e.g. Cisubuh, Parigi, CBA")
    depth_md = models.DecimalField("Depth MD (m)", max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["proposal_id", "order"]

    def __str__(self):
        return f"{self.name} @ {self.depth_md} m"


class TubeLengthRange(models.Model):
    """Tube length range entries (R-1, R-2, R-3, SP) for a proposal."""

    proposal = models.ForeignKey(
        Proposal, on_delete=models.CASCADE, related_name="tube_length_ranges"
    )
    label = models.CharField(max_length=10, help_text="R-1, R-2, R-3, SP")
    avg_length_m = models.DecimalField("Avg length (m)", max_digits=6, decimal_places=2)

    class Meta:
        ordering = ["proposal_id", "label"]

    def __str__(self):
        return f"{self.label}: {self.avg_length_m} m"


class OperationalRate(models.Model):
    """Operational rates from A.Proposal (rows 46-50, cols P-W).
    Used in drilling time calculations for tripping, casing running, etc."""

    proposal = models.ForeignKey(
        Proposal, on_delete=models.CASCADE, related_name="operational_rates"
    )
    rate_name = models.CharField(
        max_length=120,
        help_text="e.g. LENGTH PER STAND, RATE FOR RIH/POOH BHA & TBG",
    )
    value = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(
        max_length=30,
        help_text="e.g. MTR, MIN/STDS, MIN/JTS",
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["proposal_id", "order"]

    def __str__(self):
        return f"{self.rate_name}: {self.value} {self.unit}"


class CompletionSpec(models.Model):
    """Completion specification (Section 6 of A.Proposal)."""

    proposal = models.OneToOneField(
        Proposal, on_delete=models.CASCADE, related_name="completion_spec"
    )
    salt_type = models.CharField(max_length=60, blank=True, default="CaCl2")
    sg = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    yield_value = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    volume = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Completion fluid volume (bbls)",
    )
    packaging_kg_per_sax = models.DecimalField(
        "Packaging (kg/sax)", max_digits=6, decimal_places=2, null=True, blank=True
    )
    perforation_intervals = models.TextField(blank=True)


class CoringInterval(models.Model):
    """Coring interval entries for a completion spec."""

    completion_spec = models.ForeignKey(
        CompletionSpec, on_delete=models.CASCADE, related_name="coring_intervals"
    )
    order = models.PositiveIntegerField(default=0)
    depth_from_m = models.DecimalField(
        "Depth from (m)", max_digits=10, decimal_places=2, null=True, blank=True
    )
    depth_to_m = models.DecimalField(
        "Depth to (m)", max_digits=10, decimal_places=2, null=True, blank=True
    )
    coring_mtrg_m = models.DecimalField(
        "Coring meterage (m)", max_digits=8, decimal_places=2, null=True, blank=True
    )
    oh_section_inch = models.DecimalField(
        "OH section (inch)", max_digits=6, decimal_places=3, null=True, blank=True
    )

    class Meta:
        ordering = ["completion_spec_id", "order"]

    def __str__(self):
        return f"Coring {self.depth_from_m}–{self.depth_to_m} m"


class ApprovalAction(models.TextChoices):
    SUBMIT = "SUBMIT", "Submit to supervisor"
    FORWARD = "FORWARD", "Forward to management"
    REQUEST_REVISION = "REQUEST_REVISION", "Request revision"
    APPROVE = "APPROVE", "Approve"
    REJECT = "REJECT", "Reject"


class ApprovalLog(models.Model):
    proposal = models.ForeignKey(
        Proposal, on_delete=models.CASCADE, related_name="approval_logs"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    action = models.CharField(max_length=20, choices=ApprovalAction.choices)
    comment = models.TextField(blank=True)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} — {self.actor} {self.action}"
