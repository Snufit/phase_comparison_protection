from django import forms

from core.models import Line, CurrentTransformer, VoltageTransformer, LineType


class LineSelectionForm(forms.Form):
    """Форма выбора ЛЭП из выпадающего списка с фильтрами."""

    line_type_filter = forms.ModelChoiceField(
        queryset=LineType.objects.exclude(type_code="Неизвестно").order_by("type_code"),
        label="Тип ЛЭП",
        required=False,  # false - не обязательное поле
        empty_label="Все типы",  # Первый пункт "Все типы"
        widget=forms.Select(
            attrs={"class": "form-select", "id": "id_line_type_filter"}
        ),
    )

    voltage_filter = forms.ChoiceField(
        label="Напряжение, кВ",
        required=False,  # false - не обязательное поле
        choices=[("", "Все напряжения")],
        widget=forms.Select(attrs={"class": "form-select", "id": "id_voltage_filter"}),
    )

    line = forms.ModelChoiceField(
        queryset=Line.objects.all().order_by("dispatch_name"),
        label="Защищаемая ЛЭП",
        empty_label="ЛЭП не выбрана",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_line"}),
    )

    def __init__(self, *args, **kwargs):
        project_name = kwargs.pop("project_name", None)
        super().__init__(*args, **kwargs)

        # Фильтруем линии по проекту, если проект указан
        if project_name:
            queryset = Line.objects.filter(project_name=project_name).order_by(
                "dispatch_name"
            )
            self.fields["line"].queryset = queryset
        else:
            # Если проект не указан, показываем все линии (для обратной совместимости)
            self.fields["line"].queryset = Line.objects.all().order_by("dispatch_name")

        # Динамически заполняем список напряжений для выбранного проекта
        voltage_queryset = Line.objects.exclude(voltage_level__isnull=True).exclude(
            voltage_level=0
        )
        if project_name:
            voltage_queryset = voltage_queryset.filter(project_name=project_name)
        voltages = (
            voltage_queryset.values_list("voltage_level", flat=True)
            .distinct()
            .order_by("voltage_level")
        )

        # Формируем список напряжений без опции "Все напряжения" (она будет только как placeholder)
        voltage_choices = []
        # Форматируем напряжение без десятичных знаков (если целое число)
        for v in voltages:
            # Преобразуем Decimal в float, затем проверяем, целое ли это число
            v_float = float(v)
            if v_float == int(v_float):
                # Целое число - отображаем без десятичных знаков
                voltage_choices.append((str(v), f"{int(v_float)} кВ"))
            else:
                # Дробное число - отображаем как есть
                voltage_choices.append((str(v), f"{v} кВ"))
        self.fields["voltage_filter"].choices = voltage_choices


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
        widget=forms.NumberInput(
            attrs={
                "class": "form-control form-control-lg",
                "min": 0,
                "max": 5000,
                "step": 100,
            }
        ),
    )
    ct = forms.ModelChoiceField(
        queryset=CurrentTransformer.objects.all(),
        label="Трансформатор тока (ТТ)",
        empty_label="ТТ не выбран",
        required=True,  # Обязательное поле
        widget=forms.Select(attrs={"class": "form-select form-select-lg", "id": "id_calculation_ct"}),
    )
    vt = forms.ModelChoiceField(
        queryset=VoltageTransformer.objects.all(),
        label="Трансформатор напряжения (ТН)",
        empty_label="ТН не выбран",
        required=True,  # Обязательное поле
        widget=forms.Select(attrs={"class": "form-select form-select-lg", "id": "id_calculation_vt"}),
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
            attrs={"class": "form-control", "min": 0.9, "max": 0.95, "step": 0.05}
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
            attrs={"class": "form-control", "min": 0.9, "max": 0.95, "step": 0.05}
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
            attrs={"class": "form-control", "min": 0.9, "max": 0.95, "step": 0.05}
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


class ProjectSelectionForm(forms.Form):
    """Форма для выбора проекта PowerFactory."""

    project_name = forms.ChoiceField(
        label="Проект PowerFactory",
        required=True,
        choices=[],
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    def __init__(self, *args, **kwargs):
        available_projects = kwargs.pop("available_projects", [])
        super().__init__(*args, **kwargs)
        if available_projects:
            self.fields["project_name"].choices = [
                (name, name) for name in available_projects
            ]
        else:
            self.fields["project_name"].choices = [("", "Нет доступных проектов")]
