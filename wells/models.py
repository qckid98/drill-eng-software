"""Well metadata — maps to rows 3-20 of the `A.Proposal` sheet."""
from django.db import models


class WellType(models.TextChoices):
    VERTICAL = "VERTICAL", "Vertical"
    DIRECTIONAL = "DIRECTIONAL", "Directional"
    HORIZONTAL = "HORIZONTAL", "Horizontal"


class ProjectType(models.TextChoices):
    DRILLING_ONLY = "DRILLING_ONLY", "Drilling only"
    DRILLING_COMPLETION = "DRILLING_COMPLETION", "Drilling and Completion"
    WORKOVER = "WORKOVER", "Workover"


class WellCategory(models.TextChoices):
    EXPLORATION = "EXPLORATION", "Exploration"
    DEVELOPMENT = "DEVELOPMENT", "Development"
    APPRAISAL = "APPRAISAL", "Appraisal"


class Well(models.Model):
    name = models.CharField(max_length=120)
    cluster = models.CharField(max_length=120, blank=True, help_text="e.g. CLUSTER BDA-G3")
    location = models.CharField(max_length=120, blank=True, help_text="e.g. BDA-D1")
    field = models.CharField(max_length=120, blank=True, help_text="e.g. BANGADUA")
    basin = models.CharField(max_length=120, blank=True, help_text="e.g. JAWA BARAT")
    operator = models.CharField(max_length=120, default="PT. PERTAMINA EP")
    contract_area = models.CharField(max_length=120, default="INDONESIA / ASSET 3")

    elevation_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    target_formation = models.CharField(max_length=200, blank=True)

    surface_lat = models.CharField(max_length=50, blank=True)
    surface_lon = models.CharField(max_length=50, blank=True)
    target_lat = models.CharField(max_length=50, blank=True)
    target_lon = models.CharField(max_length=50, blank=True)

    project_type = models.CharField(
        max_length=30, choices=ProjectType.choices, default=ProjectType.DRILLING_COMPLETION
    )
    well_type = models.CharField(
        max_length=20, choices=WellType.choices, default=WellType.DIRECTIONAL
    )
    well_category = models.CharField(
        max_length=20, choices=WellCategory.choices, default=WellCategory.DEVELOPMENT
    )

    inclination_deg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    azimuth_deg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    kop_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    overlap_liner_7in_m = models.DecimalField(
        "Overlap Liner 7\"", max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Auto-calculated: depth casing sebelumnya − TOL liner 7\"",
    )
    overlap_liner_4in_m = models.DecimalField(
        "Overlap Liner 4.5\"", max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Auto-calculated: depth casing sebelumnya − TOL liner 4-1/2\"",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("name", "location")]

    def __str__(self):
        if self.location:
            return f"{self.name} — {self.location}"
        return self.name


class FormationMarker(models.Model):
    """Formation markers from A.Proposal rows 46-48 (Cisubuh, Parigi, CBA, etc.)."""

    well = models.ForeignKey(Well, on_delete=models.CASCADE, related_name="formation_markers")
    name = models.CharField(max_length=120, help_text="e.g. Cisubuh, Parigi, CBA")
    depth_m = models.DecimalField(max_digits=10, decimal_places=2, help_text="Depth in mMD")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["well_id", "order"]
        unique_together = [("well", "name")]

    def __str__(self):
        return f"{self.name} @ {self.depth_m} mMD"
