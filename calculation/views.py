from collections import defaultdict

import openpyxl
from openpyxl.styles import Font
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views import View
from django.http import HttpResponse
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages

from core.models import Line

from .forms import LineSelectionForm, CalculationFactorsForm, SubmodesConfigurationForm
from .models import CalculationMeta, SensitivityAnalysis, SettingsCalculation
from .services import (
    PowerFactoryManager,
    TopologyAnalysisService,
    SettingsCalculationService,
    SensitivityAnalysisService,
)
from .services.fault_calculation_service import FaultCalculationService
from .services.submodes_generator import generate_half_set_submodes
from .services.powerfactory_locator import get_pf_line_data, get_pf_line

FAULT_TYPE_COLORS = {
    "К(3)": {
        "backgroundColor": "rgba(54, 162, 235, 0.5)",
        "borderColor": "rgba(54, 162, 235, 1)",
    },
    "К(2)": {
        "backgroundColor": "rgba(54, 162, 235, 0.5)",
        "borderColor": "rgba(54, 162, 235, 1)",
    },
    "К(1,1)": {
        "backgroundColor": "rgba(75, 192, 192, 0.5)",
        "borderColor": "rgba(75, 192, 192, 1)",
    },
    "К(1)": {
        "backgroundColor": "rgba(255, 99, 132, 0.5)",
        "borderColor": "rgba(255, 99, 132, 1)",
    },
}


class CalculationView(LoginRequiredMixin, TemplateView):

    template_name = "calculation/calculation_new.html"
    pf_manager = PowerFactoryManager()

    def get(self, request):
        print(f"User is authenticated: {request.user.is_authenticated}")

        line_form = LineSelectionForm()
        calculation_form = CalculationFactorsForm()
        submodes_form1 = SubmodesConfigurationForm(prefix="half_set1")
        submodes_form2 = SubmodesConfigurationForm(prefix="half_set2")

        line = None
        protection_device = None
        half_set1 = None
        half_set2 = None
        half_set1_topology_display = None
        half_set2_topology_display = None
        half_set1_submodes = None
        half_set2_submodes = None
        line_id = request.session.get("line_id", None)

        if line_id:
            line = Line.objects.get(pk=line_id)
            protection_half_sets = line.protection_half_sets.all()
            half_set1 = protection_half_sets[0]
            half_set2 = protection_half_sets[1]
            protection_device = half_set1.protection_device
            half_set1_topology_display = request.session.get(
                "half_set1_topology_display"
            )
            half_set2_topology_display = request.session.get(
                "half_set2_topology_display"
            )
            line_form = LineSelectionForm(
                initial={
                    "line": line.id,
                    "ct": line.ct.id if line.ct else None,
                    "vt": line.vt.id if line.vt else None,
                }
            )
            half_set1_submodes = request.session.get("half_set1_submodes")
            half_set2_submodes = request.session.get("half_set2_submodes")

        line_data = request.session.get("line_data")

        # Начальные значения для формы подрежимов
        half_set1_topology = request.session.get("half_set1_topology")
        half_set2_topology = request.session.get("half_set2_topology")
        half_set1_topology_display = request.session.get("half_set1_topology_display")
        half_set2_topology_display = request.session.get("half_set2_topology_display")
        if (
            half_set1_topology
            and half_set2_topology
            and half_set1_topology_display
            and half_set2_topology_display
        ):

            half_set1_max_outages = (len(half_set1_topology) + 1) // 2
            half_set2_max_outages = (len(half_set2_topology) + 1) // 2

            half_set1_max_lines = (len(half_set1_topology_display.get("ЛЭП")) + 1) // 2
            half_set2_max_lines = (len(half_set2_topology_display.get("ЛЭП")) + 1) // 2

            half_set1_max_autotransformers = (
                len(half_set1_topology_display.get("АТ")) // 2
            )
            half_set2_max_autotransformers = (
                len(half_set2_topology_display.get("АТ")) // 2
            )

            submodes_form1 = SubmodesConfigurationForm(
                prefix="half_set1",
                initial={
                    "max_outages": half_set1_max_outages,
                    "max_lines": half_set1_max_lines,
                    "max_autotransformers": half_set1_max_autotransformers,
                },
            )
            submodes_form2 = SubmodesConfigurationForm(
                prefix="half_set2",
                initial={
                    "max_outages": half_set2_max_outages,
                    "max_lines": half_set2_max_lines,
                    "max_autotransformers": half_set2_max_autotransformers,
                },
            )

        calculation_factors = request.session.get("calculation_factors", None)

        if calculation_factors:
            calculation_form = CalculationFactorsForm(initial=calculation_factors)

        return render(
            request,
            self.template_name,
            {
                "line": line,
                "line_data": line_data,
                "protection_device": protection_device,
                "line_form": line_form,
                "calculation_form": calculation_form,
                "submodes_form1": submodes_form1,
                "submodes_form2": submodes_form2,
                "half_set1": half_set1,
                "half_set2": half_set2,
                "half_set1_topology_display": half_set1_topology_display,
                "half_set2_topology_display": half_set2_topology_display,
                "half_set1_submodes": half_set1_submodes,
                "half_set2_submodes": half_set2_submodes,
            },
        )

    def post(self, request):
        action = request.POST.get("action")
        if action == "select_line":
            return self.select_line(request)
        elif action == "generate_submodes":
            return self.generate_submodes(request)
        elif action == "save_calculation_factors":
            return self.save_calculation_factors(request)
        elif action == "calculate_settings":
            return self.calculate_settings(request)

        return redirect("calculation")

    def select_line(self, request):
        # request.session.clear()
        form = LineSelectionForm(request.POST)
        if form.is_valid():

            # Получаем выбранную ЛЭП с формы и сохраняем в сессию
            line = form.cleaned_data["line"]
            request.session["line_id"] = line.id

            # Сохраняем выбранные ТТ и ТН в модель Line
            ct = form.cleaned_data.get("ct")
            vt = form.cleaned_data.get("vt")
            if ct:
                line.ct = ct
            if vt:
                line.vt = vt
            if ct or vt:
                line.save()

            # Получаем полукомплекты ЛЭП
            protection_half_sets = line.protection_half_sets.all()

            # Дифференцируем полукомплекты
            half_set1 = protection_half_sets[0]
            half_set2 = protection_half_sets[1]

            # Сохраняем полукомплекты в сессии
            request.session["half_set1_id"] = half_set1.id
            request.session["half_set2_id"] = half_set2.id

            try:
                # Создаем COM-объект PowerFactory
                app = self.pf_manager.get_application()

                pf_line = get_pf_line(app, line.pf_name)
                pf_line_data = get_pf_line_data(pf_line)
                request.session["line_data"] = pf_line_data

                # Получаем напряжение ЛЭП из PowerFactory и сохраняем в модель
                line.update_voltage_from_pf(app)

                # Выполняем анализ топологии прилегающей
                # сети для каждого полукомплекта
                topology_service1 = TopologyAnalysisService(half_set1)
                topology_service2 = TopologyAnalysisService(half_set2)
                half_set1_topology = topology_service1.get_half_set_topology(app)
                half_set2_topology = topology_service2.get_half_set_topology(app)

                # Освобождаем COM-объект
                # print(app.GetAttributes())

                # Сохраняем сырую топологию для передачи в сервисы в сессии
                request.session["half_set1_topology"] = half_set1_topology
                request.session["half_set2_topology"] = half_set2_topology

                # Преобразуем топологии для отображения на странице
                half_set1_topology_display = self.process_half_set_topology(
                    half_set1_topology
                )
                half_set2_topology_display = self.process_half_set_topology(
                    half_set2_topology
                )

                # Сохраняем топологии для отображения на странице в сессии
                request.session["half_set1_topology_display"] = (
                    half_set1_topology_display
                )
                request.session["half_set2_topology_display"] = (
                    half_set2_topology_display
                )
            except ModuleNotFoundError as e:
                messages.error(request, str(e))
                return redirect("calculation")

        return redirect("calculation")

    def generate_submodes(self, request):
        submodes_form1 = SubmodesConfigurationForm(request.POST, prefix="half_set1")
        submodes_form2 = SubmodesConfigurationForm(request.POST, prefix="half_set2")

        if submodes_form1.is_valid() and submodes_form2.is_valid():

            half_set1_submodes_data = submodes_form1.cleaned_data
            half_set2_submodes_data = submodes_form2.cleaned_data

            print(half_set1_submodes_data)
            print(half_set2_submodes_data)

            half_set1_topology = request.session.get("half_set1_topology")
            half_set2_topology = request.session.get("half_set2_topology")

            half_set1_submodes = generate_half_set_submodes(
                half_set1_topology, half_set1_submodes_data
            )
            half_set2_submodes = generate_half_set_submodes(
                half_set2_topology, half_set2_submodes_data
            )

            print(half_set1_submodes)
            print(half_set2_submodes)

            # Сохраняем подрежимы в сессии
            request.session["half_set1_submodes"] = half_set1_submodes
            request.session["half_set2_submodes"] = half_set2_submodes

            messages.success(request, "Подрежимы успешно сгенерированы.")

        return redirect("calculation")

    def save_calculation_factors(self, request):
        form = CalculationFactorsForm(request.POST)
        if form.is_valid():
            calculation_factors = form.cleaned_data
            print(calculation_factors)
            request.session["calculation_factors"] = calculation_factors
            messages.success(request, "Коэффициенты успешно сохранены.")
        return redirect("calculation")

    def calculate_settings(self, request):
        print("Начало расчета")
        half_set1_submodes = request.session.get("half_set1_submodes")
        half_set2_submodes = request.session.get("half_set2_submodes")
        calculation_factors = request.session.get("calculation_factors")
        line_id = request.session.get("line_id", None)

        line = Line.objects.get(pk=line_id)
        protection_half_sets = line.protection_half_sets.all()
        half_set1 = protection_half_sets[0]
        half_set2 = protection_half_sets[1]

        # Создаем экземпляр сервиса расчета токов КЗ
        fault_service = FaultCalculationService()

        # Регистрируем расчет
        calculation_meta = CalculationMeta.objects.create(line=line, user=request.user)

        # Создаем COM-объект PowerFactory
        app = self.pf_manager.get_application()

        # Выполняем расчет токов КЗ
        fault_service.perform_fault_calculation(
            app, half_set1, half_set1_submodes, calculation_meta
        )
        fault_service.perform_fault_calculation(
            app, half_set2, half_set2_submodes, calculation_meta
        )

        # Освобождаем COM-объект
        del app

        # Выполняем расчет параметров настройки ДФЗ
        calculation_service = SettingsCalculationService(
            calculation_meta, calculation_factors
        )
        calculation_service.run()

        # Выполняем расчет чувствительности
        sensitivity_service = SensitivityAnalysisService(calculation_meta)
        sensitivity_service.run()

        return redirect("results", calculation_meta_id=calculation_meta.id)

    def process_half_set_topology(self, half_set_topology):
        half_set_topology_display = {"ЛЭП": [], "АТ": []}
        for element in half_set_topology:
            loc_name = element.get("loc_name")
            element_type = element.get("type")
            if element_type == "ЛЭП":
                half_set_topology_display["ЛЭП"].append(loc_name)
            elif element_type == "АТ":
                half_set_topology_display["АТ"].append(loc_name)
        return half_set_topology_display


class TestView(View):

    template_name = "calculation/calculation_test.html"

    def get(self, request):

        coefficients = request.session.get(
            "coefficients", {"coefficient1": 1.3, "coefficient2": 1.2}
        )
        result = request.session.get("result", None)

        return render(
            request,
            self.template_name,
            {"coefficients": coefficients, "result": result},
        )

    def post(self, request):

        action = request.POST.get("action")

        if action == "save":
            coefficient1 = float(request.POST.get("coefficient1", 0))
            coefficient2 = float(request.POST.get("coefficient2", 0))
            request.session["coefficients"] = {
                "coefficient1": coefficient1,
                "coefficient2": coefficient2,
            }
            return redirect("test")

        elif action == "calculate":
            coefficients = request.session.get("coefficients", None)
            coefficient1 = coefficients["coefficient1"]
            coefficient2 = coefficients["coefficient2"]
            result = round(coefficient1 * coefficient2, 2)
            request.session["result"] = result
            if "coefficients" in request.session:
                del request.session["coefficients"]
            return redirect("test")


def calculation_results(request, calculation_meta_id):
    calculation_meta = CalculationMeta.objects.get(id=calculation_meta_id)
    results = SettingsCalculation.objects.filter(
        calculation_meta=calculation_meta
    ).order_by("protection_half_set")
    return render(
        request,
        "calculation/results.html",
        {"results": results, "calculation_meta": calculation_meta},
    )


def sensitivity_analysis(request, calculation_meta_id):
    calculation_meta = CalculationMeta.objects.get(id=calculation_meta_id)
    sens_analysis = SensitivityAnalysis.objects.filter(
        settings_calculation__calculation_meta=calculation_meta
    )
    
    # Добавляем пагинацию
    paginator = Paginator(sens_analysis, 15)  # 10 записей на страницу
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    return render(
        request,
        "calculation/sensitivity_analysis.html",
        {
            "page_obj": page_obj,
            "calculation_meta": calculation_meta,
            "sens_analysis": sens_analysis,
        },
    )


def calculation_list(request):
    calculations = CalculationMeta.objects.all().order_by("-calculation_date")
    paginator = Paginator(calculations, 18)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    return render(request, "calculation/calculation_list.html", {"page_obj": page_obj})


def sensitivity_chart_view(request):

    component_id = request.GET.get("component_id")
    half_set_id = request.GET.get("half_set_id")

    # Фильтруем результаты по выбранному органу и полукомплекту
    sens_analysis = SensitivityAnalysis.objects.filter(
        settings_calculation__component_id=component_id,
        settings_calculation__protection_half_set_id=half_set_id,
    ).select_related("fault_calculation")

    # Группировка данных по 'network_topology' и 'fault_type'
    grouped_data = defaultdict(lambda: defaultdict(float))
    fault_types = set()

    for s in sens_analysis:
        topology = str(s.fault_calculation.network_topology)
        fault_type = str(s.fault_calculation.fault_type)
        grouped_data[topology][fault_type] = s.sensitivity_rate
        fault_types.add(fault_type)

    # Подготовка данных для графика
    fault_types = sorted(fault_types)  # Упорядочить типы КЗ
    labels = sorted(grouped_data.keys())  # Упорядочить схемы
    datasets = []

    for fault_type in fault_types:
        color = FAULT_TYPE_COLORS.get(
            fault_type,
            {
                "backgroundColor": "rgba(201, 203, 207, 0.5)",
                "borderColor": "rgba(201, 203, 207, 1)",
            },
        )
        datasets.append(
            {
            "label": fault_type,
                "data": [
                    grouped_data[topology].get(fault_type, 0) for topology in labels
                ],
            "backgroundColor": color["backgroundColor"],
            "borderColor": color["borderColor"],
            "borderWidth": 1,
            }
        )

    data = {
        "labels": labels,
        "datasets": datasets,
    }

    context = {
        "data": data,
        "component_id": component_id,
        "half_set_id": half_set_id,
    }
    return render(request, "calculation/sensitivity_chart.html", context)


def export_sensitivity_analysis(request, calculation_meta_id):
    calculation_meta = CalculationMeta.objects.get(id=calculation_meta_id)
    sens_analysis = SensitivityAnalysis.objects.filter(
        settings_calculation__calculation_meta=calculation_meta
    )

    # Создаем рабочую книгу
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Анализ чувствительности"

    # Заголовки
    headers = [
        "Полукомплект",
        "Орган ДФЗ",
        "Схема",
        "Вид КЗ",
        "Чувствительность",
        "Статус",
    ]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = Font(bold=True)

    # Данные
    for row_num, result in enumerate(sens_analysis, start=2):
        ws.cell(
            row=row_num,
            column=1,
            value=str(result.settings_calculation.protection_half_set),
        )
        ws.cell(row=row_num, column=2, value=str(result.settings_calculation.component))
        ws.cell(row=row_num, column=3, value=result.fault_calculation.network_topology)
        ws.cell(row=row_num, column=4, value=result.fault_calculation.fault_type)
        ws.cell(row=row_num, column=5, value=result.sensitivity_rate)
        ws.cell(row=row_num, column=6, value=result.status)

    # Создаем HTTP-ответ
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="sensitivity_analysis_{calculation_meta.id}.xlsx"'
    )
    wb.save(response)

    return response


def export_calculation_results(request, calculation_meta_id):
    calculation_meta = CalculationMeta.objects.get(id=calculation_meta_id)
    calculations = SettingsCalculation.objects.filter(calculation_meta=calculation_meta)

    # Создаем рабочую книгу
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Расчет параметров настройки"

    # Заголовки
    headers = [
        "Полукомплект",
        "Орган ДФЗ",
        "Коэффициенты",
        "Значение уставки (первичное)",
        "Значение уставки (вторичное)",
    ]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.font = Font(bold=True)

    # Заполняем данными
    for row_num, calculation in enumerate(calculations, start=2):
        coefficients = (
            "\n".join(
                f"{key}: {value}"
                for key, value in calculation.calculation_factors.items()
            )
            if calculation.calculation_factors
            else "Нет коэффициентов"
        )

        ws.cell(row=row_num, column=1, value=str(calculation.protection_half_set))
        ws.cell(row=row_num, column=2, value=str(calculation.component))
        ws.cell(row=row_num, column=3, value=coefficients)
        ws.cell(row=row_num, column=4, value=calculation.result_value)

    # Создаем HTTP-ответ с файлом Excel
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="calculation_results_{calculation_meta.id}.xlsx"'
    )
    
    wb.save(response)
    return response
