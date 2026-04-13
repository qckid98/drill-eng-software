from django import forms

from .models import AFE, AFELine


TEXT_INPUT = forms.TextInput(attrs={"class": "input"})
NUMBER_INPUT = forms.NumberInput(attrs={"class": "input", "step": "0.01"})


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


class AFEApprovalActionForm(forms.Form):
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "input",
                                      "placeholder": "Komentar (opsional)"}),
    )


class RateCardUploadForm(forms.Form):
    excel_file = forms.FileField(label="AFE workbook (.xlsx)",
                                   help_text="Sheet D.MATE akan di-reimport.")
