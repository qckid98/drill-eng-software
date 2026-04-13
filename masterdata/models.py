"""
Master data models, seeded from the source workbook
`DrillTime_ BDA-G3 - Cluster BDA-D1.xlsx`.

Everything in this app is reference data that Drilling Engineers *pick*
from when composing a proposal (hole sections, mud types, activity library,
ROP benchmarks, rigs). Nothing in this app is proposal-specific.
"""

from django.db import models


class PhaseType(models.TextChoices):
    DRILLING = "DRILLING", "Drilling"
    NON_DRILLING = "NON_DRILLING", "Non-drilling"
    COMPLETION = "COMPLETION", "Completion"


class HoleSection(models.Model):
    """One of the canonical hole sizes used in the casing design table."""

    size_inch = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        unique=True,
        help_text="Hole / open hole size in inches (e.g. 26, 17.5, 12.25)",
    )
    label = models.CharField(max_length=30, help_text='Display label, e.g. "26\\""')
    default_od = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    default_id = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    default_weight_lbs_ft = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-size_inch"]

    def __str__(self):
        return self.label


class MudType(models.Model):
    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class RopRate(models.Model):
    """Rate of penetration benchmark for a depth interval (from ROP sheet)."""

    hole_section = models.ForeignKey(HoleSection, on_delete=models.CASCADE, related_name="rop_rates")
    start_depth_m = models.DecimalField(max_digits=8, decimal_places=2)
    end_depth_m = models.DecimalField(max_digits=8, decimal_places=2)
    days = models.DecimalField(max_digits=6, decimal_places=2)
    rop_m_per_day = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        ordering = ["hole_section__size_inch", "start_depth_m"]

    def __str__(self):
        return f"{self.hole_section} {self.start_depth_m}-{self.end_depth_m} m @ {self.rop_m_per_day} m/d"


class ActivityCategoryL1(models.Model):
    """Top-level drilling phase, e.g. 'RIG UP / RIG DOWN', 'DRILLING FORMATION & CEMENT'."""

    name = models.CharField(max_length=150, unique=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Activity Category Level 1"
        verbose_name_plural = "Activity Categories Level 1"

    def __str__(self):
        return self.name


class ActivityCategoryL2(models.Model):
    """Sub-phase under an L1 category (e.g. 'Rig Move Rig 1500 HP 50 KM')."""

    parent = models.ForeignKey(
        ActivityCategoryL1, on_delete=models.CASCADE, related_name="children"
    )
    name = models.CharField(max_length=250)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["parent__order", "order", "name"]
        unique_together = [("parent", "name")]
        verbose_name = "Activity Category Level 2"
        verbose_name_plural = "Activity Categories Level 2"

    def __str__(self):
        return f"{self.parent.name} / {self.name}"


class DrillingActivity(models.Model):
    """
    Individual activity line from Tab 1.0 — the atomic unit of drilling work
    that shows up as a row inside a proposal's activity list.
    """

    category_l2 = models.ForeignKey(
        ActivityCategoryL2, on_delete=models.CASCADE, related_name="activities"
    )
    code = models.CharField(max_length=20, blank=True, help_text="Excel 'Code' column (e.g. 1b, 2b)")
    description = models.CharField(max_length=500)
    default_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        help_text="Baseline hours from Tab 1.0 STD column",
    )
    phase_type = models.CharField(
        max_length=20, choices=PhaseType.choices, default=PhaseType.DRILLING
    )
    applies_to_hole_sections = models.ManyToManyField(
        HoleSection, blank=True, related_name="activities",
        help_text="If empty, activity applies to all hole sections",
    )

    class Meta:
        ordering = ["category_l2__parent__order", "category_l2__order", "code", "description"]
        indexes = [models.Index(fields=["phase_type"])]

    def __str__(self):
        return f"[{self.code or '-'}] {self.description[:60]}"


class RigSpec(models.Model):
    """Physical rig that performs the work."""

    platform_name = models.CharField(max_length=100, unique=True)
    horsepower = models.PositiveIntegerField(null=True, blank=True)
    floor_height_m = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    capacity = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["platform_name"]
        verbose_name = "Rig specification"
        verbose_name_plural = "Rig specifications"

    def __str__(self):
        return self.platform_name
