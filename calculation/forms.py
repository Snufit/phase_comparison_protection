from django import forms

from core.models import Line, CurrentTransformer, VoltageTransformer


class LineSelectionForm(forms.Form):
    """Форма выбора ЛЭП из выпадающего списка."""

    line = forms.ModelChoiceField(
        queryset=Line.objects.all(),
        label="Защищаемая ЛЭП",
        empty_label="ЛЭП не выбрана",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    ct = forms.ModelChoiceField(
        queryset=CurrentTransformer.objects.all(),
        label="Трансформатор тока (ТТ)",
        empty_label="ТТ не выбран",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    vt = forms.ModelChoiceField(
        queryset=VoltageTransformer.objects.all(),
        label="Трансформатор напряжения (ТН)",
        empty_label="ТН не выбран",
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class SubmodesConfigurationForm(forms.Form):
    """Форма для задания ограничений по подрежимам."""

    min_outages = forms.IntegerField(
        label="Минимальное число отключений",
        required=True,
        initial=0,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 0, "step": 1.0}
        ),
    )
    max_outages = forms.IntegerField(
        label="Максимальное число отключений",
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 0, "step": 1.0}
        ),
    )
    max_lines = forms.IntegerField(
        label="Максимальное число отключенных ЛЭП",
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 0, "step": 1.0}
        ),
    )
    max_autotransformers = forms.IntegerField(
        label="Максимальное число отключенных АТ",
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 0, "step": 1.0}
        ),
    )


class CalculationFactorsForm(forms.Form):
    """Форма для ввода расчетных коэффициентов."""

    load_current = forms.FloatField(
        label="Длительно допустимый рабочий ток, А",
        initial=2000,
        required=True,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": 100}),
    )
    il_grading_factor = forms.FloatField(
        label="Коэффициент отстройки",
        initial=1.3,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1.2, "max": 2.0, "step": 0.1}
        ),
    )
    il_reset_factor = forms.FloatField(
        label="Коэффициент возврата",
        initial=0.9,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 0.8, "max": 1.0, "step": 0.01}
        ),
    )
    il_matching_factor = forms.FloatField(
        label="Коэффициент согласования",
        initial=1.4,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1.4, "max": 2.0, "step": 0.1}
        ),
    )
    i2_imbalance_factor = forms.FloatField(
        label="Коэффициент небаланса",
        initial=0.05,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 0.02, "max": 0.05, "step": 0.01}
        ),
    )
    i2_grading_factor = forms.FloatField(
        label="Коэффициент отстройки",
        initial=1.3,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1.2, "max": 2.0, "step": 0.1}
        ),
    )
    i2_reset_factor = forms.FloatField(
        label="Коэффициент возврата",
        initial=0.9,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 0.8, "max": 1.0, "step": 0.01}
        ),
    )
    i2_matching_factor = forms.FloatField(
        label="Коэффициент согласования",
        initial=1.4,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1.4, "max": 2.0, "step": 0.1}
        ),
    )
    di1_matching_factor = forms.FloatField(
        label="Коэффициент согласования",
        initial=1.4,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1.4, "max": 2.0, "step": 0.1}
        ),
    )
    u2_grading_factor = forms.FloatField(
        label="Коэффициент отстройки",
        initial=1.3,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1.2, "max": 2.0, "step": 0.1}
        ),
    )
    u2_reset_factor = forms.FloatField(
        label="Коэффициент возврата",
        initial=0.9,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 0.8, "max": 1.0, "step": 0.01}
        ),
    )
    u2_imbalance_voltage = forms.FloatField(
        label="Напряжение небаланса",
        initial=1.5,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1.5, "max": 2.0, "step": 0.1}
        ),
    )
    u2_matching_factor = forms.FloatField(
        label="Коэффициент согласования",
        initial=2.0,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1.4, "max": 2.0, "step": 0.1}
        ),
    )
    manipulation_grading_factor = forms.FloatField(
        label="Коэффициент надежности",
        initial=1.5,
        required=True,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 1.5, "max": 2.0, "step": 0.1}
        ),
    )
