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
    tol_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        help_text="Time on Location override (hours). Leave 0 to use activity sum.",
    )
    mud_type = models.ForeignKey(
        MudType, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_completion = models.BooleanField(
        default=False,
        help_text="Check if this row represents the completion phase (not dry hole).",
    )
    notes = models.CharField(max_length=255, blank=True)

    # cached totals (refreshed by calc.py whenever activities change)
    drilling_days = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    non_drilling_days = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    total_days = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    drilling_rate_m_per_day = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    class Meta:
        ordering = ["proposal_id", "order"]

    def __str__(self):
        return f"{self.hole_section} @ {self.depth_m} m"

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


class TubingSpec(models.Model):
    """Production string tubing specification (Section 4 of A.Proposal)."""

    proposal = models.OneToOneField(
        Proposal, on_delete=models.CASCADE, related_name="tubing_spec"
    )
    od_inch = models.DecimalField(
        "OD (inch)", max_digits=6, decimal_places=3, null=True, blank=True
    )
    id_inch = models.DecimalField(
        "ID (inch)", max_digits=6, decimal_places=3, null=True, blank=True
    )
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_length = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    formation_marker = models.CharField(max_length=120, blank=True)
    depth_md = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)


class CompletionSpec(models.Model):
    """Completion specification (Section 6 of A.Proposal)."""

    proposal = models.OneToOneField(
        Proposal, on_delete=models.CASCADE, related_name="completion_spec"
    )
    salt_type = models.CharField(max_length=60, blank=True, default="CaCl2")
    sg = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    yield_value = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    coring_depth_from = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    coring_depth_to = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    perforation_intervals = models.TextField(blank=True)


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
