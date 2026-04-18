from django import forms
from django.db import models as db_models

from wells.models import Well, FormationMarker
from masterdata.models import (
    ActivityCategoryL1,
    ActivityCategoryL2,
    DrillingActivity,
    HoleSection,
    MudType,
    RigSpec,
)

from .models import (
    CasingSection,
    CompletionSpec,
    CoringInterval,
    OperationalRate,
    Proposal,
    ProposalActivity,
    TubeLengthRange,
    TubingItem,
)


TEXT_INPUT = forms.TextInput(attrs={"class": "input"})
NUMBER_INPUT = forms.NumberInput(attrs={"class": "input", "step": "0.01"})
SELECT = forms.Select(attrs={"class": "input"})


class WellForm(forms.ModelForm):
    class Meta:
        model = Well
        fields = [
            "name", "cluster", "location", "field", "basin",
            "elevation_m", "target_formation",
            "surface_lat", "surface_lon", "target_lat", "target_lon",
            "project_type", "well_type", "well_category",
            "inclination_deg", "azimuth_deg", "kop_m",
        ]
        widgets = {f: TEXT_INPUT for f in [
            "name", "cluster", "location", "field", "basin",
            "target_formation", "surface_lat", "surface_lon",
            "target_lat", "target_lon",
        ]}


class ProposalGeneralForm(forms.ModelForm):
    class Meta:
        model = Proposal
        fields = [
            "title", "rig", "date_input", "spud_date", "completion_date",
            "mob_days", "demob_days", "dollar_rate",
        ]
        widgets = {
            "title": TEXT_INPUT,
            "date_input": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "spud_date": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "completion_date": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "mob_days": NUMBER_INPUT,
            "demob_days": NUMBER_INPUT,
            "dollar_rate": NUMBER_INPUT,
        }


class CasingSectionForm(forms.ModelForm):
    class Meta:
        model = CasingSection
        fields = [
            "order", "hole_section", "od_csg", "id_csg", "weight_lbs_ft",
            "depth_m", "top_of_liner_m", "mud_type", "is_completion", "notes",
            "sg_from", "sg_to", "casing_type", "pounder", "thread",
            "range_spec", "section_type",
        ]
        widgets = {
            "od_csg": NUMBER_INPUT,
            "id_csg": NUMBER_INPUT,
            "weight_lbs_ft": NUMBER_INPUT,
            "depth_m": NUMBER_INPUT,
            "top_of_liner_m": NUMBER_INPUT,
            "sg_from": NUMBER_INPUT,
            "sg_to": NUMBER_INPUT,
            "pounder": NUMBER_INPUT,
            "notes": TEXT_INPUT,
            "casing_type": TEXT_INPUT,
            "thread": TEXT_INPUT,
            "range_spec": TEXT_INPUT,
            "section_type": TEXT_INPUT,
        }


CasingSectionFormSet = forms.inlineformset_factory(
    Proposal, CasingSection,
    form=CasingSectionForm,
    extra=1, can_delete=True,
)


class ProposalActivityForm(forms.ModelForm):
    class Meta:
        model = ProposalActivity
        fields = ["order", "activity", "hours_override", "notes"]
        widgets = {
            "hours_override": NUMBER_INPUT,
            "notes": TEXT_INPUT,
        }

    def __init__(self, *args, hole_section=None, **kwargs):
        super().__init__(*args, **kwargs)
        if hole_section is not None:
            # Show activities that either:
            # 1. Have no hole_section restriction (generic), OR
            # 2. Are linked to this specific hole section
            self.fields["activity"].queryset = (
                DrillingActivity.objects.filter(
                    db_models.Q(applies_to_hole_sections__isnull=True)
                    | db_models.Q(applies_to_hole_sections=hole_section)
                ).distinct()
            )


def _make_activity_formset(hole_section=None):
    """Create a ProposalActivityFormSet that filters activities by hole section."""

    class _Form(ProposalActivityForm):
        def __init__(self, *args, **kwargs):
            kwargs["hole_section"] = hole_section
            super().__init__(*args, **kwargs)

    return forms.inlineformset_factory(
        CasingSection, ProposalActivity,
        form=_Form,
        extra=3, can_delete=True,
    )


# Default formset (no filtering) for backward compatibility
ProposalActivityFormSet = forms.inlineformset_factory(
    CasingSection, ProposalActivity,
    form=ProposalActivityForm,
    extra=3, can_delete=True,
)


class TubingItemForm(forms.ModelForm):
    class Meta:
        model = TubingItem
        fields = ["order", "od_inch", "id_inch", "weight_lbs_ft", "avg_length_m", "depth_md"]
        widgets = {
            "od_inch": NUMBER_INPUT,
            "id_inch": NUMBER_INPUT,
            "weight_lbs_ft": NUMBER_INPUT,
            "avg_length_m": NUMBER_INPUT,
            "depth_md": NUMBER_INPUT,
        }


TubingItemFormSet = forms.inlineformset_factory(
    Proposal, TubingItem,
    form=TubingItemForm,
    extra=1, can_delete=True,
)

# Backward-compatible aliases
TubingSpecForm = TubingItemForm
TubingSpecFormSet = TubingItemFormSet


class OperationalRateForm(forms.ModelForm):
    class Meta:
        model = OperationalRate
        fields = ["order", "rate_name", "value", "unit"]
        widgets = {
            "rate_name": TEXT_INPUT,
            "value": NUMBER_INPUT,
            "unit": TEXT_INPUT,
        }


OperationalRateFormSet = forms.inlineformset_factory(
    Proposal, OperationalRate,
    form=OperationalRateForm,
    extra=1, can_delete=True,
)


class FormationMarkerForm(forms.ModelForm):
    class Meta:
        model = FormationMarker
        fields = ["order", "name", "depth_m"]
        widgets = {
            "name": TEXT_INPUT,
            "depth_m": NUMBER_INPUT,
        }


FormationMarkerFormSet = forms.inlineformset_factory(
    Well, FormationMarker,
    form=FormationMarkerForm,
    extra=1, can_delete=True,
)


class CompletionSpecForm(forms.ModelForm):
    class Meta:
        model = CompletionSpec
        fields = [
            "salt_type", "sg", "yield_value", "volume",
            "packaging_kg_per_sax", "perforation_intervals",
        ]


class CoringIntervalForm(forms.ModelForm):
    class Meta:
        model = CoringInterval
        fields = ["order", "depth_from_m", "depth_to_m", "coring_mtrg_m", "oh_section_inch"]
        widgets = {
            "depth_from_m": NUMBER_INPUT,
            "depth_to_m": NUMBER_INPUT,
            "coring_mtrg_m": NUMBER_INPUT,
            "oh_section_inch": NUMBER_INPUT,
        }


CoringIntervalFormSet = forms.inlineformset_factory(
    CompletionSpec, CoringInterval,
    form=CoringIntervalForm,
    extra=1, can_delete=True,
)


class TubeLengthRangeForm(forms.ModelForm):
    class Meta:
        model = TubeLengthRange
        fields = ["label", "avg_length_m"]
        widgets = {
            "label": TEXT_INPUT,
            "avg_length_m": NUMBER_INPUT,
        }


TubeLengthRangeFormSet = forms.inlineformset_factory(
    Proposal, TubeLengthRange,
    form=TubeLengthRangeForm,
    extra=1, can_delete=True,
)


class ApprovalActionForm(forms.Form):
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "input", "placeholder": "Komentar (opsional)"}),
    )
