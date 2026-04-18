from django import forms

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
    OperationalRate,
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
            "overlap_liner_7in_m", "overlap_liner_4in_m",
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
            "depth_m", "tol_hours", "mud_type", "is_completion", "notes",
            "sg_from", "sg_to", "casing_type", "pounder", "thread",
            "range_spec", "section_type",
        ]
        widgets = {
            "od_csg": NUMBER_INPUT,
            "id_csg": NUMBER_INPUT,
            "weight_lbs_ft": NUMBER_INPUT,
            "depth_m": NUMBER_INPUT,
            "tol_hours": NUMBER_INPUT,
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


ProposalActivityFormSet = forms.inlineformset_factory(
    CasingSection, ProposalActivity,
    form=ProposalActivityForm,
    extra=3, can_delete=True,
)


class TubingSpecForm(forms.ModelForm):
    class Meta:
        model = TubingSpec
        fields = ["order", "od_inch", "id_inch", "weight", "avg_length", "depth_md"]
        widgets = {
            "od_inch": NUMBER_INPUT,
            "id_inch": NUMBER_INPUT,
            "weight": NUMBER_INPUT,
            "avg_length": NUMBER_INPUT,
            "depth_md": NUMBER_INPUT,
        }


TubingSpecFormSet = forms.inlineformset_factory(
    Proposal, TubingSpec,
    form=TubingSpecForm,
    extra=1, can_delete=True,
)


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
            "coring_depth_from", "coring_depth_to", "perforation_intervals",
        ]


class ApprovalActionForm(forms.Form):
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "input", "placeholder": "Komentar (opsional)"}),
    )
