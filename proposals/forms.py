from django import forms

from wells.models import Well
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
    Proposal,
    ProposalActivity,
    TubingSpec,
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
            "title", "rig", "spud_date", "completion_date",
            "mob_days", "demob_days", "dollar_rate",
        ]
        widgets = {
            "title": TEXT_INPUT,
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
            "depth_m", "tol_hours", "mud_type", "is_completion", "notes",
        ]
        widgets = {
            "od_csg": NUMBER_INPUT,
            "id_csg": NUMBER_INPUT,
            "weight_lbs_ft": NUMBER_INPUT,
            "depth_m": NUMBER_INPUT,
            "tol_hours": NUMBER_INPUT,
            "notes": TEXT_INPUT,
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


ProposalActivityFormSet = forms.inlineformset_factory(
    CasingSection, ProposalActivity,
    form=ProposalActivityForm,
    extra=3, can_delete=True,
)


class TubingSpecForm(forms.ModelForm):
    class Meta:
        model = TubingSpec
        fields = ["od_inch", "id_inch", "weight", "avg_length", "formation_marker", "depth_md"]


class CompletionSpecForm(forms.ModelForm):
    class Meta:
        model = CompletionSpec
        fields = [
            "salt_type", "sg", "yield_value",
            "coring_depth_from", "coring_depth_to", "perforation_intervals",
        ]


class ApprovalActionForm(forms.Form):
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "input", "placeholder": "Komentar (opsional)"}),
    )
