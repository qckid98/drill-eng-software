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
    CoringInterval,
    FormationMarker,
    Proposal,
    ProposalActivity,
    ProposalPhaseActivity,
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
            "overlap_liner_7_m", "overlap_liner_4_5_m",
        ]
        widgets = {
            **{f: TEXT_INPUT for f in [
                "name", "cluster", "location", "field", "basin",
                "target_formation", "surface_lat", "surface_lon",
                "target_lat", "target_lon",
            ]},
            "overlap_liner_7_m": NUMBER_INPUT,
            "overlap_liner_4_5_m": NUMBER_INPUT,
        }


class ProposalGeneralForm(forms.ModelForm):
    class Meta:
        model = Proposal
        fields = [
            "title", "no_afe", "well_status", "rig",
            "spud_date", "completion_date",
            "placed_into_service", "closed_out_date",
            "mob_days", "demob_days",
            "jarak_moving_km", "interval_total_perfo_m",
            "dollar_rate",
        ]
        widgets = {
            "title": TEXT_INPUT,
            "no_afe": TEXT_INPUT,
            "well_status": TEXT_INPUT,
            "spud_date": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "completion_date": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "placed_into_service": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "input"}),
            "closed_out_date": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "input"}),
            "mob_days": NUMBER_INPUT,
            "demob_days": NUMBER_INPUT,
            "jarak_moving_km": NUMBER_INPUT,
            "interval_total_perfo_m": NUMBER_INPUT,
            "dollar_rate": NUMBER_INPUT,
        }


class CasingSectionForm(forms.ModelForm):
    class Meta:
        model = CasingSection
        fields = [
            "order", "hole_section", "od_csg", "id_csg", "weight_lbs_ft",
            "depth_m", "top_of_liner_m", "mud_type", "sg_from", "sg_to",
            "is_completion", "notes",
        ]
        widgets = {
            "od_csg": NUMBER_INPUT,
            "id_csg": NUMBER_INPUT,
            "weight_lbs_ft": NUMBER_INPUT,
            "depth_m": NUMBER_INPUT,
            "top_of_liner_m": NUMBER_INPUT,
            "sg_from": NUMBER_INPUT,
            "sg_to": NUMBER_INPUT,
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


class ProposalPhaseActivityForm(forms.ModelForm):
    class Meta:
        model = ProposalPhaseActivity
        fields = ["order", "activity", "hours_override", "notes"]
        widgets = {
            "hours_override": NUMBER_INPUT,
            "notes": TEXT_INPUT,
        }


ProposalPhaseActivityFormSet = forms.inlineformset_factory(
    Proposal, ProposalPhaseActivity,
    form=ProposalPhaseActivityForm,
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


class FormationMarkerForm(forms.ModelForm):
    class Meta:
        model = FormationMarker
        fields = ["order", "name", "depth_md"]
        widgets = {
            "name": TEXT_INPUT,
            "depth_md": NUMBER_INPUT,
        }


FormationMarkerFormSet = forms.inlineformset_factory(
    Proposal, FormationMarker,
    form=FormationMarkerForm,
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


class CompletionSpecForm(forms.ModelForm):
    class Meta:
        model = CompletionSpec
        fields = [
            "salt_type", "sg", "yield_value",
            "packaging_kg_per_sax", "perforation_intervals",
        ]
        widgets = {
            "salt_type": TEXT_INPUT,
            "sg": NUMBER_INPUT,
            "yield_value": NUMBER_INPUT,
            "packaging_kg_per_sax": NUMBER_INPUT,
        }


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


class ApprovalActionForm(forms.Form):
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "input", "placeholder": "Komentar (opsional)"}),
    )
