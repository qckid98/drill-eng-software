from django import forms

from .models import AFE, AFELine, AFELineComponent, AFETemplate, RateCardItem


TEXT_INPUT = forms.TextInput(attrs={"class": "input"})
NUMBER_INPUT = forms.NumberInput(attrs={"class": "input", "step": "0.01"})
SELECT = forms.Select(attrs={"class": "input"})


class AFEHeaderForm(forms.ModelForm):
    class Meta:
        model = AFE
        fields = ["title", "contingency_percent", "exchange_rate_override"]
        widgets = {
            "title": TEXT_INPUT,
            "contingency_percent": NUMBER_INPUT,
            "exchange_rate_override": NUMBER_INPUT,
        }


class AFELineForm(forms.ModelForm):
    class Meta:
        model = AFELine
        fields = ["override_usd", "notes"]
        widgets = {
            "override_usd": forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
            "notes": TEXT_INPUT,
        }


AFELineFormSet = forms.inlineformset_factory(
    AFE, AFELine,
    form=AFELineForm,
    extra=0, can_delete=False,
)


# ---------------------------------------------------------------------------
# Rate Card CRUD
# ---------------------------------------------------------------------------
class RateCardItemForm(forms.ModelForm):
    class Meta:
        model = RateCardItem
        fields = [
            "code", "description", "unit_of_measure", "unit_price_usd",
            "afe_line", "phase_flag", "material_type",
            "effective_from", "effective_to", "notes",
        ]
        widgets = {
            "code": TEXT_INPUT,
            "description": forms.TextInput(attrs={"class": "input", "style": "min-width:300px"}),
            "unit_of_measure": TEXT_INPUT,
            "unit_price_usd": NUMBER_INPUT,
            "afe_line": SELECT,
            "phase_flag": SELECT,
            "material_type": TEXT_INPUT,
            "effective_from": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "effective_to": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "notes": TEXT_INPUT,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show AFE line choices with line_code + name
        self.fields["afe_line"].queryset = AFETemplate.objects.filter(
            is_subtotal_row=False
        ).order_by("order")
        self.fields["afe_line"].required = False


# ---------------------------------------------------------------------------
# AFE Line Component inline editing
# ---------------------------------------------------------------------------
class AFELineComponentForm(forms.ModelForm):
    class Meta:
        model = AFELineComponent
        fields = [
            "description", "quantity", "unit_of_measure",
            "unit_price_usd", "material_type", "phase_flag", "order",
        ]
        widgets = {
            "description": forms.TextInput(attrs={"class": "input", "style": "min-width:200px"}),
            "quantity": NUMBER_INPUT,
            "unit_of_measure": forms.TextInput(attrs={"class": "input", "style": "width:60px"}),
            "unit_price_usd": NUMBER_INPUT,
            "material_type": forms.TextInput(attrs={"class": "input", "style": "width:80px"}),
            "phase_flag": SELECT,
            "order": forms.NumberInput(attrs={"class": "input", "style": "width:50px"}),
        }


AFELineComponentFormSet = forms.inlineformset_factory(
    AFELine, AFELineComponent,
    form=AFELineComponentForm,
    extra=1, can_delete=True,
)


# ---------------------------------------------------------------------------
# Approval + Upload
# ---------------------------------------------------------------------------
class AFEApprovalActionForm(forms.Form):
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "input",
                                      "placeholder": "Komentar (opsional)"}),
    )


class RateCardUploadForm(forms.Form):
    excel_file = forms.FileField(
        label="AFE workbook (.xlsx)",
        help_text="Sheet D.MATE akan di-reimport. Data rate card yang sudah ada akan di-update.",
        widget=forms.FileInput(attrs={"class": "input", "accept": ".xlsx,.xls"}),
    )
