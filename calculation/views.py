from collections import defaultdict
import copy

import openpyxl
from openpyxl.styles import Font
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views import View
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
import json
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
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
from .services.settings_calculation_map import SETTINGS_CALCULATION_MAP
from .services.project_sync_service import ProjectSyncService
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
    template_name = "calculation/calculation.html"
    pf_manager = PowerFactoryManager()

    def get(self, request):
        FaultCalculationService._log(f"User is authenticated: {request.user.is_authenticated}")

        # Получаем проект из сессии для фильтрации данных
        project_name = request.session.get("pf_project_name")
        line_id = request.session.get("line_id", None)

        # Создаем форму и устанавливаем начальные значения
        line_form = LineSelectionForm(project_name=project_name)

        calculation_form = CalculationFactorsForm()
        submodes_form1 = SubmodesConfigurationForm(prefix="half_set1")
        submodes_form2 = SubmodesConfigurationForm(prefix="half_set2")

        line = None
        protection_device = None
        methodology = None
        half_set1 = None
        half_set2 = None
        half_set1_topology_display = None
        half_set2_topology_display = None
        half_set1_submodes = None
        half_set2_submodes = None

        # Если выбрана ЛЭП, устанавливаем начальные значения для формы коэффициентов
        if line_id:
            try:
                line_query = Line.objects.filter(pk=line_id)
                if project_name:
                    line_query = line_query.filter(project_name=project_name)
                line = line_query.first()

                # Если у линии есть ТТ и ТН, устанавливаем их в форме коэффициентов
                if line:
                    if line.ct:
                        calculation_form.fields["ct"].initial = line.ct
                    if line.vt:
                        calculation_form.fields["vt"].initial = line.vt
                    # Если у линии нет ТН, но есть напряжение, пытаемся найти подходящий
                    elif line.voltage_level:
                        from core.models import VoltageTransformer

                        line_voltage_int = int(float(line.voltage_level))
                        # Ищем ТН с primary_voltage, соответствующим напряжению ЛЭП
                        # Например: 110 кВ -> ТН 110000/100 (primary_voltage = 110)
                        vt_queryset = VoltageTransformer.objects.filter(
                            primary_voltage=line_voltage_int
                        ).order_by('id')
                        
                        if vt_queryset.exists():
                            vt = vt_queryset.first()
                            FaultCalculationService._log(
                                f"[DEBUG] Автоматически выбран ТН для ЛЭП {line.dispatch_name}: {vt} "
                                f"(напряжение ЛЭП: {line.voltage_level} кВ, primary_voltage ТН: {vt.primary_voltage} кВ)"
                            )
                            calculation_form.fields["vt"].initial = vt
                        else:
                            FaultCalculationService._log(
                                f"[WARNING] ТН с primary_voltage={line_voltage_int} кВ не найден для ЛЭП {line.dispatch_name} "
                                f"при загрузке страницы"
                            )
            except Line.DoesNotExist:
                pass

        if line_id:
            try:
                # Фильтруем линию по проекту, если проект выбран
                line_query = Line.objects.filter(pk=line_id)
                if project_name:
                    line_query = line_query.filter(project_name=project_name)
                line = line_query.get()
                protection_half_sets = list(line.protection_half_sets.all())

                # Проверяем наличие полукомплектов защиты
                if len(protection_half_sets) < 2:
                    # Очищаем сессию для этой линии, так как нет полукомплектов
                    request.session.pop("line_id", None)
                    request.session.pop("half_set1_id", None)
                    request.session.pop("half_set2_id", None)
                    request.session.pop("line_data", None)
                    messages.error(
                        request,
                        f"Для ЛЭП '{line.dispatch_name}' не найдено полукомплектов защиты. "
                        f"Найдено: {len(protection_half_sets)}, требуется: 2. "
                        f"Пожалуйста, создайте полукомплекты защиты с помощью команды: "
                        f"python manage.py create_protection_half_sets_for_all_lines --line-id {line.id}",
                    )
                    # Сбрасываем line_id, чтобы не пытаться загружать данные для этой линии
                    line_id = None
                    line = None
                else:
                    half_set1 = protection_half_sets[0]
                    half_set2 = protection_half_sets[1]
                    protection_device = half_set1.protection_device

                    # Получаем методику с учетом напряжения ЛЭП
                    if protection_device and line:
                        methodology = protection_device.get_methodology_by_voltage(
                            line.voltage_level
                        )
                    else:
                        methodology = (
                            protection_device.methodology if protection_device else None
                        )
            except (Line.DoesNotExist, IndexError):
                # Если линия не найдена или нет полукомплектов, очищаем сессию
                request.session.pop("line_id", None)
                request.session.pop("half_set1_id", None)
                request.session.pop("half_set2_id", None)
                request.session.pop("line_data", None)
                line_id = None
                line = None

            # Получаем данные для отображения из сессии
            half_set1_topology_display = request.session.get(
                "half_set1_topology_display"
            )
            half_set2_topology_display = request.session.get(
                "half_set2_topology_display"
            )
            # Получаем подрежимы из сессии
            half_set1_submodes = request.session.get("half_set1_submodes")
            half_set2_submodes = request.session.get("half_set2_submodes")

        FaultCalculationService._log(
            f"[DEBUG] Подрежимы из сессии - half_set1: {half_set1_submodes is not None}, half_set2: {half_set2_submodes is not None}"
        )

        # Если подрежимы отсутствуют в сессии, пытаемся загрузить из БД
        if not half_set1_submodes and half_set1:
            try:
                from calculation.models import HalfSetSubmode

                db_submodes = HalfSetSubmode.objects.filter(
                    protection_half_set=half_set1
                ).order_by("id")
                if db_submodes.exists():
                    half_set1_submodes = [
                        {
                            "submode_name": s.submode_name,
                            "submode_elements": s.submode_elements,
                        }
                        for s in db_submodes
                    ]
                    # Сохраняем в сессию для последующих запросов
                    request.session["half_set1_submodes"] = half_set1_submodes
            except Exception as e:
                FaultCalculationService._log(
                    f"[DEBUG] Ошибка при загрузке подрежимов из БД для half_set1: {e}"
                )

        if not half_set2_submodes and half_set2:
            try:
                from calculation.models import HalfSetSubmode

                db_submodes = HalfSetSubmode.objects.filter(
                    protection_half_set=half_set2
                ).order_by("id")
                if db_submodes.exists():
                    half_set2_submodes = [
                        {
                            "submode_name": s.submode_name,
                            "submode_elements": s.submode_elements,
                        }
                        for s in db_submodes
                    ]
                    # Сохраняем в сессию для последующих запросов
                    request.session["half_set2_submodes"] = half_set2_submodes
            except Exception as e:
                FaultCalculationService._log(
                    f"[DEBUG] Ошибка при загрузке подрежимов из БД для half_set2: {e}"
                )

        line_data = request.session.get("line_data")

        # Начальные значения для формы подрежимов
        # Пытаемся получить топологию из сессии или БД
        half_set1_topology = request.session.get("half_set1_topology")
        half_set2_topology = request.session.get("half_set2_topology")

        # Если нет в сессии, пытаемся получить из БД
        if not half_set1_topology and half_set1:
            try:
                topology_service1 = TopologyAnalysisService(half_set1)
                half_set1_topology = topology_service1.get_half_set_topology(
                    app=None, force_refresh=False
                )
                request.session["half_set1_topology"] = half_set1_topology
            except (ModuleNotFoundError, RuntimeError):
                pass

        if not half_set2_topology and half_set2:
            try:
                topology_service2 = TopologyAnalysisService(half_set2)
                half_set2_topology = topology_service2.get_half_set_topology(
                    app=None, force_refresh=False
                )
                request.session["half_set2_topology"] = half_set2_topology
            except (ModuleNotFoundError, RuntimeError):
                pass

        # Преобразуем топологии для отображения, если они есть
        if half_set1_topology:
            half_set1_topology_display = self.process_half_set_topology(
                half_set1_topology
            )
            request.session["half_set1_topology_display"] = half_set1_topology_display
        else:
            half_set1_topology_display = request.session.get(
                "half_set1_topology_display"
            )

        if half_set2_topology:
            half_set2_topology_display = self.process_half_set_topology(
                half_set2_topology
            )
            request.session["half_set2_topology_display"] = half_set2_topology_display
        else:
            half_set2_topology_display = request.session.get(
                "half_set2_topology_display"
            )
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
            # Восстанавливаем форму с сохраненными коэффициентами
            calculation_form = CalculationFactorsForm(initial=calculation_factors)
            # Если в сессии есть ТТ и ТН, устанавливаем их
            if line:
                if line.ct:
                    calculation_form.fields["ct"].initial = line.ct
                if line.vt:
                    calculation_form.fields["vt"].initial = line.vt

        # Получаем подстанции ответвлений для линии
        branch_substations = []
        if line:
            # Получаем все активные ответвления
            branches = (
                line.branches.filter(is_active=True)
                .select_related("substation")
                .order_by("id")
            )

            for branch in branches:
                if branch.substation:
                    # Используем pf_name или строковое представление подстанции
                    substation_name = branch.substation.pf_name or str(
                        branch.substation
                    )
                    branch_substations.append(substation_name)
                elif branch.pf_name_substation:
                    branch_substations.append(branch.pf_name_substation)

            # Если ответвлений нет, но есть pf_name, попробуем обновить ответвления из PowerFactory
            # Это может быть полезно для параллельных линий, где ответвления могут быть не сохранены
            if not branch_substations and line.pf_name:
                try:
                    project_name = request.session.get("pf_project_name")
                    app = self.pf_manager.get_application(project_name=project_name)
                    line.update_branches_from_pf(app)
                    # Повторно получаем ответвления после обновления
                    branches = (
                        line.branches.filter(is_active=True)
                        .select_related("substation")
                        .order_by("id")
                    )
                    for branch in branches:
                        if branch.substation:
                            substation_name = branch.substation.pf_name or str(
                                branch.substation
                            )
                            branch_substations.append(substation_name)
                        elif branch.pf_name_substation:
                            branch_substations.append(branch.pf_name_substation)
                except Exception:
                    # Если не удалось обновить (например, PowerFactory недоступен), просто игнорируем ошибку
                    pass

        # Получаем методику с учетом напряжения ЛЭП, если еще не получена
        if protection_device and line and not methodology:
            methodology = protection_device.get_methodology_by_voltage(
                line.voltage_level
            )
        elif protection_device and not methodology:
            methodology = protection_device.methodology

        # Проверяем наличие ответвлений у линии
        has_branches = False
        if line:
            # Проверяем наличие активных ответвлений
            has_branches = line.branches.filter(is_active=True).exists()
            # Если ответвлений нет в БД, но есть branch_substations, значит они есть
            if not has_branches and branch_substations:
                has_branches = True

        # Подготавливаем данные для отображения всех органов и их коэффициентов
        # Группируем органы по типам ЛЭП
        organs_by_line_type = {
            "Основные органы": [
                # Токовые органы
                "IЛ БЛОК",
                "IЛ ОТКЛ",
                "I2 БЛОК",
                "I2 ОТКЛ",
                "3I0 БЛОК",
                "3I0 ОТКЛ",  # Не важны, но важны на ЛЭП с ответвлениями
                # Органы по приращению тока
                "DI1 БЛОК",
                "DI1 ОТКЛ",
                "DI2 БЛОК",
                "DI2 ОТКЛ",
                # Напряженческие органы (необязательные)
                "U2 БЛОК",
                "U2 ОТКЛ",
                # Дистанционный орган
                "R ОТКЛ",
                "X ОТКЛ",
                # Управляющие органы
                "K МАН",  # Коэффициент комбинированного фильтра
                "УГОЛ БЛОК",  # Угол блокировки ОСФ
            ],
            "Специальные органы": [
                # Дистанционный орган защиты ответвлений
                "R ОТВ",
                "X ОТВ",
                # Направленный орган мощности нулевой последовательности
                "РТНП/3I0_M0",
                "РННП/3U0_M0",
            ],
        }

        # Органы, которые можно включать/отключать
        # Для 3I0 - важны на ЛЭП с ответвлениями
        # Для DI1, DI2, U2 - можно включать/отключать на любой ЛЭП (необязательные органы)
        toggleable_organs = {
            "3I0 БЛОК": {"important_with_branches": True, "default_enabled": False},
            "3I0 ОТКЛ": {"important_with_branches": True, "default_enabled": False},
            "DI1 БЛОК": {"important_with_branches": False, "default_enabled": False},
            "DI1 ОТКЛ": {"important_with_branches": False, "default_enabled": False},
            "DI2 БЛОК": {"important_with_branches": False, "default_enabled": False},
            "DI2 ОТКЛ": {"important_with_branches": False, "default_enabled": False},
            "U2 БЛОК": {"important_with_branches": False, "default_enabled": False},
            "U2 ОТКЛ": {"important_with_branches": False, "default_enabled": False},
        }

        # Словарь для отображения названий органов (если нужно изменить отображаемое название)
        organ_display_names = {
            "K МАН": "Орган манипуляции",
            "УГОЛ БЛОК": "Орган сравнения фаз",
        }

        # Получаем состояние включения/отключения органов из сессии
        enabled_organs = request.session.get("enabled_organs", {})

        # Формируем структуру данных для отображения
        organs_data = {}
        calculation_factors = request.session.get("calculation_factors", {})
        for category, organ_names in organs_by_line_type.items():
            # Пропускаем категорию специальных органов, если нет ответвлений
            if (
                category
                == "Специальные органы (используются ТОЛЬКО на ЛЭП С ответвлениями)"
                and not has_branches
            ):
                continue

            organs_data[category] = []
            for organ_name in organ_names:
                # Пропускаем специальные органы, если нет ответвлений
                if (
                    organ_name in ["R ОТВ", "X ОТВ", "РТНП/3I0_M0", "РННП/3U0_M0"]
                    and not has_branches
                ):
                    continue

                # Определяем состояние включения/отключения для переключаемых органов
                is_enabled = True
                if organ_name in toggleable_organs:
                    organ_config = toggleable_organs[organ_name]
                    # Если орган важен на ЛЭП с ответвлениями и они есть, включаем по умолчанию
                    if organ_config["important_with_branches"] and has_branches:
                        is_enabled = enabled_organs.get(organ_name, True)
                    else:
                        is_enabled = enabled_organs.get(
                            organ_name, organ_config["default_enabled"]
                        )

                if organ_name in SETTINGS_CALCULATION_MAP:
                    organ_info = copy.deepcopy(SETTINGS_CALCULATION_MAP[organ_name])
                    # Используем отображаемое название, если оно есть, иначе оригинальное
                    organ_info["name"] = organ_display_names.get(organ_name, organ_name)
                    # Сохраняем оригинальное название для идентификации
                    organ_info["original_name"] = organ_name
                    # Добавляем информацию о том, можно ли переключать орган
                    if organ_name in toggleable_organs:
                        organ_info["toggleable"] = True
                        organ_info["enabled"] = is_enabled
                    # Получаем текущие значения коэффициентов из сессии, если они есть
                    if organ_info.get("calculation_factors"):
                        for factor_key, factor_data in organ_info[
                            "calculation_factors"
                        ].items():
                            # Всегда устанавливаем current_value: либо из сессии, либо из default_value
                            if factor_key in calculation_factors:
                                # Используем значение из сессии
                                factor_data["current_value"] = calculation_factors[
                                    factor_key
                                ]
                            else:
                                # Используем default_value как значение для отображения
                                # Убеждаемся, что default_value существует и не None
                                default_val = factor_data.get("default_value")
                                # Всегда устанавливаем current_value равным default_value
                                # Если default_value отсутствует, оставляем None (шаблон обработает)
                                factor_data["current_value"] = default_val
                    organs_data[category].append(organ_info)

        # Получаем все методики для отображения в модальном окне
        from core.models import MethodologyDocument

        all_methodologies = (
            MethodologyDocument.objects.all().order_by("-created_at")
            if MethodologyDocument
            else []
        )

        # Группируем методики по производителям
        methodologies_by_manufacturer = {
            "ЭКРА": [],
            "Релематика": [],
            "Бреслер": [],
            "Другие": [],
        }

        for meth in all_methodologies:
            name_file_lower = meth.name_file.lower()
            # Проверяем путь файла - если он содержит папку производителя, используем её
            # Формат: methodologies/ЭКРА/файл.pdf или methodologies/Релематика/файл.pdf
            path_parts = name_file_lower.replace("\\", "/").split("/")

            # Ищем папку производителя в пути (обычно это второй элемент после 'methodologies')
            if len(path_parts) >= 2 and path_parts[0] == "methodologies":
                manufacturer_in_path = path_parts[1]
                if "экра" in manufacturer_in_path:
                    methodologies_by_manufacturer["ЭКРА"].append(meth)
                elif "релематика" in manufacturer_in_path:
                    methodologies_by_manufacturer["Релематика"].append(meth)
                elif "бреслер" in manufacturer_in_path or "нпп" in manufacturer_in_path:
                    methodologies_by_manufacturer["Бреслер"].append(meth)
                else:
                    methodologies_by_manufacturer["Другие"].append(meth)
            else:
                # Для обратной совместимости: проверяем имя файла, если путь не содержит папку
                if "экра" in name_file_lower:
                    methodologies_by_manufacturer["ЭКРА"].append(meth)
                elif "релематика" in name_file_lower:
                    methodologies_by_manufacturer["Релематика"].append(meth)
                elif "бреслер" in name_file_lower or "нпп" in name_file_lower:
                    methodologies_by_manufacturer["Бреслер"].append(meth)
                else:
                    methodologies_by_manufacturer["Другие"].append(meth)

        # Удаляем пустые категории
        methodologies_by_manufacturer = {
            k: v for k, v in methodologies_by_manufacturer.items() if v
        }

        return render(
            request,
            self.template_name,
            {
                "line": line,
                "line_data": line_data,
                "protection_device": protection_device,
                "methodology": methodology,
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
                "branch_substations": branch_substations,
                "organs_data": organs_data,
                "settings_calculation_map": SETTINGS_CALCULATION_MAP,
                "all_methodologies": all_methodologies,
                "methodologies_by_manufacturer": methodologies_by_manufacturer,
                "has_branches": has_branches,
                "toggleable_organs": toggleable_organs,
            },
        )

    def post(self, request):
        action = request.POST.get("action")
        if action == "select_project":
            return self.select_project(request)
        elif action == "select_line":
            return self.select_line(request)
        elif action == "generate_submodes":
            return self.generate_submodes(request)
        elif action == "save_calculation_factors":
            return self.save_calculation_factors(request)
        elif action == "toggle_organ":
            return self.toggle_organ(request)
        elif action == "calculate_settings":
            return self.calculate_settings(request)

        return redirect("calculation")

    def select_project(self, request):
        """
        Обрабатывает выбор проекта PowerFactory пользователем и синхронизирует данные.
        """
        project_name = request.POST.get("project_name")
        if project_name:
            # Проверяем доступность проекта
            if self.pf_manager.check_project_available(project_name):
                try:
                    # Сохраняем в сессию
                    request.session["pf_project_name"] = project_name

                    # Проверяем, нужна ли синхронизация
                    sync_service = ProjectSyncService(project_name=project_name)

                    if sync_service.needs_sync():
                        # Запускаем синхронизацию проекта с БД
                        messages.info(
                            request,
                            f"Начинается синхронизация проекта '{project_name}' с базой данных. "
                            "Это может занять некоторое время...",
                        )
                        # Выполняем синхронизацию
                        results = sync_service.sync_project(force_full=False)
                    else:
                        # Данные уже есть, только обновляем
                        messages.info(
                            request, f"Обновление данных проекта '{project_name}'..."
                        )
                        results = sync_service.sync_project(force_full=False)

                    # Формируем сообщение о результатах
                    if results.get("skipped"):
                        messages.info(
                            request,
                            results.get("message", "Данные проекта уже актуальны."),
                        )
                    else:
                        total_errors = (
                            results["lines"]["errors"]
                            + results["substations"]["errors"]
                            + results["branches"]["errors"]
                            + results["half_sets"]["errors"]
                            + results["topology"]["errors"]
                        )

                        if total_errors == 0:
                            result_msg = (
                                f"Проект '{project_name}' успешно обновлен! "
                                f"Линии: {results['lines']['created']} создано, {results['lines']['updated']} обновлено. "
                                f"Подстанции: {results['substations']['created']} создано, {results['substations']['updated']} обновлено. "
                            )
                            if results["branches"]["filled"] > 0:
                                result_msg += f"Ответвления: {results['branches']['filled']} заполнено. "
                            if results["half_sets"]["created"] > 0:
                                result_msg += f"Полукомплекты: {results['half_sets']['created']} создано. "
                            if results["topology"]["analyzed"] > 0:
                                result_msg += f"Топология: {results['topology']['analyzed']} проанализировано."
                            messages.success(request, result_msg)
                        else:
                            result_msg = (
                                f"Проект '{project_name}' обновлен с предупреждениями. "
                                f"Линии: {results['lines']['created']} создано, {results['lines']['updated']} обновлено. "
                                f"Подстанции: {results['substations']['created']} создано. "
                                f"Обнаружено ошибок: {total_errors}."
                            )
                            messages.warning(request, result_msg)

                except Exception as e:
                    messages.error(
                        request,
                        f"Ошибка при синхронизации проекта '{project_name}': {str(e)}",
                    )
                    # Оставляем проект в сессии, но предупреждаем об ошибке
            else:
                messages.error(request, f"Проект '{project_name}' недоступен")
                # Очищаем сессию, если проект недоступен
                request.session.pop("pf_project_name", None)
        else:
            messages.error(request, "Не выбран проект")

        return redirect("calculation")

    def select_line(self, request):
        # request.session.clear()
        project_name = request.session.get("pf_project_name")
        form = LineSelectionForm(request.POST, project_name=project_name)
        if form.is_valid():
            # Получаем выбранную ЛЭП с формы и сохраняем в сессию
            line = form.cleaned_data["line"]
            request.session["line_id"] = line.id

            # Получаем полукомплекты ЛЭП
            protection_half_sets = list(line.protection_half_sets.all())

            # Проверяем наличие полукомплектов защиты
            if len(protection_half_sets) < 2:
                messages.error(
                    request,
                    f"Для ЛЭП '{line.dispatch_name}' не найдено полукомплектов защиты. "
                    f"Найдено: {len(protection_half_sets)}, требуется: 2. "
                    f"Пожалуйста, создайте полукомплекты защиты с помощью команды: "
                    f"python manage.py create_protection_half_sets_for_all_lines --line-id {line.id}",
                )
                return redirect("calculation")

            # Дифференцируем полукомплекты
            half_set1 = protection_half_sets[0]
            half_set2 = protection_half_sets[1]

            # Сохраняем полукомплекты в сессии
            request.session["half_set1_id"] = half_set1.id
            request.session["half_set2_id"] = half_set2.id

            try:
                # Создаем COM-объект PowerFactory
                project_name = request.session.get("pf_project_name")
                app = self.pf_manager.get_application(project_name=project_name)

                pf_line = get_pf_line(app, line.pf_name)
                pf_line_data = get_pf_line_data(pf_line)
                request.session["line_data"] = pf_line_data

                # Получаем напряжение ЛЭП из PowerFactory и сохраняем в модель
                line.update_voltage_from_pf(app)

                # Если ТН еще не установлен, пытаемся найти подходящий по напряжению
                # Например: 110 кВ -> ТН 110000/100 (primary_voltage = 110)
                if not line.vt and line.voltage_level:
                    from core.models import VoltageTransformer

                    # Ищем ТН с primary_voltage, соответствующим напряжению ЛЭП
                    line_voltage_int = int(float(line.voltage_level))
                    vt_queryset = VoltageTransformer.objects.filter(
                        primary_voltage=line_voltage_int
                    ).order_by('id')
                    
                    if vt_queryset.exists():
                        vt = vt_queryset.first()
                        FaultCalculationService._log(
                            f"[DEBUG] Автоматически найден ТН для ЛЭП {line.dispatch_name} при выборе линии: {vt} "
                            f"(напряжение ЛЭП: {line.voltage_level} кВ, primary_voltage ТН: {vt.primary_voltage} кВ)"
                        )
                        line.vt = vt
                        line.save()
                    else:
                        FaultCalculationService._log(
                            f"[WARNING] ТН с primary_voltage={line_voltage_int} кВ не найден для ЛЭП {line.dispatch_name} "
                            f"при выборе линии. Напряжение ЛЭП: {line.voltage_level} кВ"
                        )

                # Выполняем анализ топологии прилегающей
                # сети для каждого полукомплекта
                # Сначала пытаемся получить из БД, если нет - из PowerFactory
                topology_service1 = TopologyAnalysisService(half_set1)
                topology_service2 = TopologyAnalysisService(half_set2)

                # Пытаемся получить топологию из БД (без подключения к PF)
                try:
                    half_set1_topology = topology_service1.get_half_set_topology(
                        app=None, force_refresh=False
                    )
                    half_set2_topology = topology_service2.get_half_set_topology(
                        app=None, force_refresh=False
                    )
                except (ModuleNotFoundError, RuntimeError):
                    # Если нет в БД или PowerFactory недоступен, используем переданный app
                    half_set1_topology = topology_service1.get_half_set_topology(
                        app=app, force_refresh=False
                    )
                    half_set2_topology = topology_service2.get_half_set_topology(
                        app=app, force_refresh=False
                    )

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
                request.session[
                    "half_set1_topology_display"
                ] = half_set1_topology_display
                request.session[
                    "half_set2_topology_display"
                ] = half_set2_topology_display
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

            FaultCalculationService._log(str(half_set1_submodes_data))
            FaultCalculationService._log(str(half_set2_submodes_data))

            half_set1_topology = request.session.get("half_set1_topology")
            half_set2_topology = request.session.get("half_set2_topology")

            # Получаем полукомплекты из сессии
            line_id = request.session.get("line_id")
            project_name = request.session.get("pf_project_name")
            if line_id:
                from core.models import Line

                line_query = Line.objects.filter(id=line_id)
                if project_name:
                    line_query = line_query.filter(project_name=project_name)
                line = line_query.get()
                protection_half_sets = line.protection_half_sets.all()
                half_set1 = (
                    protection_half_sets[0] if len(protection_half_sets) > 0 else None
                )
                half_set2 = (
                    protection_half_sets[1] if len(protection_half_sets) > 1 else None
                )
            else:
                half_set1 = None
                half_set2 = None

            half_set1_submodes = generate_half_set_submodes(
                half_set1_topology,
                half_set1_submodes_data,
                protection_half_set=half_set1,
                use_cache=True,
            )
            half_set2_submodes = generate_half_set_submodes(
                half_set2_topology,
                half_set2_submodes_data,
                protection_half_set=half_set2,
                use_cache=True,
            )

            FaultCalculationService._log(str(half_set1_submodes))
            FaultCalculationService._log(str(half_set2_submodes))

            # Сохраняем подрежимы в сессии
            # Убеждаемся, что подрежимы - это список словарей (сериализуемый формат)
            if half_set1_submodes:
                # Преобразуем в список словарей, если это необходимо
                half_set1_submodes_list = []
                for submode in half_set1_submodes:
                    if isinstance(submode, dict):
                        half_set1_submodes_list.append(
                            {
                                "submode_name": str(submode.get("submode_name", "")),
                                "submode_elements": list(
                                    submode.get("submode_elements", [])
                                ),
                            }
                        )
                    else:
                        # Если это объект модели, преобразуем в словарь
                        half_set1_submodes_list.append(
                            {
                                "submode_name": str(
                                    getattr(submode, "submode_name", "")
                                ),
                                "submode_elements": list(
                                    getattr(submode, "submode_elements", [])
                                ),
                            }
                        )
                request.session["half_set1_submodes"] = half_set1_submodes_list
                FaultCalculationService._log(
                    f"[DEBUG] Сохранено подрежимов для half_set1: {len(half_set1_submodes_list)}"
                )

            if half_set2_submodes:
                # Преобразуем в список словарей, если это необходимо
                half_set2_submodes_list = []
                for submode in half_set2_submodes:
                    if isinstance(submode, dict):
                        half_set2_submodes_list.append(
                            {
                                "submode_name": str(submode.get("submode_name", "")),
                                "submode_elements": list(
                                    submode.get("submode_elements", [])
                                ),
                            }
                        )
                    else:
                        # Если это объект модели, преобразуем в словарь
                        half_set2_submodes_list.append(
                            {
                                "submode_name": str(
                                    getattr(submode, "submode_name", "")
                                ),
                                "submode_elements": list(
                                    getattr(submode, "submode_elements", [])
                                ),
                            }
                        )
                request.session["half_set2_submodes"] = half_set2_submodes_list
                FaultCalculationService._log(
                    f"[DEBUG] Сохранено подрежимов для half_set2: {len(half_set2_submodes_list)}"
                )

            # Явно сохраняем сессию
            request.session.modified = True
            FaultCalculationService._log(
                f"[DEBUG] Сессия сохранена. half_set1_submodes в сессии: {request.session.get('half_set1_submodes') is not None}"
            )
            FaultCalculationService._log(
                f"[DEBUG] Сессия сохранена. half_set2_submodes в сессии: {request.session.get('half_set2_submodes') is not None}"
            )

            messages.success(
                request,
                f"Подрежимы успешно сгенерированы. Полукомплект 1: {len(half_set1_submodes) if half_set1_submodes else 0}, Полукомплект 2: {len(half_set2_submodes) if half_set2_submodes else 0}.",
            )

        return redirect("calculation")

    def save_calculation_factors(self, request):
        # Собираем все коэффициенты из POST запроса
        calculation_factors = {}

        # Получаем линию из сессии
        line_id = request.session.get("line_id")
        project_name = request.session.get("pf_project_name")
        line = None
        if line_id:
            line_query = Line.objects.filter(pk=line_id)
            if project_name:
                line_query = line_query.filter(project_name=project_name)
            line = line_query.first()

        # Сначала получаем данные из стандартной формы
        form = CalculationFactorsForm(request.POST)
        if form.is_valid():
            calculation_factors.update(form.cleaned_data)
            
            # Сохраняем выбранные ТТ и ТН в модель Line
            ct = form.cleaned_data.get("ct")
            vt = form.cleaned_data.get("vt")
            
            if line:
                # Если ТН не выбран пользователем, но у линии есть напряжение,
                # пытаемся найти подходящий ТН автоматически
                # Например: 110 кВ -> ТН 110000/100 (primary_voltage = 110)
                if not vt and line.voltage_level:
                    from core.models import VoltageTransformer

                    # Ищем ТН с primary_voltage, соответствующим напряжению ЛЭП
                    line_voltage_int = int(float(line.voltage_level))
                    vt_queryset = VoltageTransformer.objects.filter(
                        primary_voltage=line_voltage_int
                    ).order_by('id')
                    
                    if vt_queryset.exists():
                        vt = vt_queryset.first()
                        FaultCalculationService._log(
                            f"[DEBUG] Автоматически найден ТН для ЛЭП {line.dispatch_name}: {vt} "
                            f"(напряжение ЛЭП: {line.voltage_level} кВ, primary_voltage ТН: {vt.primary_voltage} кВ)"
                        )
                        line.vt = vt
                    else:
                        FaultCalculationService._log(
                            f"[WARNING] ТН с primary_voltage={line_voltage_int} кВ не найден для ЛЭП {line.dispatch_name} "
                            f"при сохранении коэффициентов"
                        )

                if ct:
                    line.ct = ct
                if vt:
                    line.vt = vt
                if ct or vt:
                    line.save()

        # Сохраняем состояние включения/отключения органов
        enabled_organs = {}
        toggleable_organs_list = [
            "3I0 БЛОК",
            "3I0 ОТКЛ",
            "DI1 БЛОК",
            "DI1 ОТКЛ",
            "DI2 БЛОК",
            "DI2 ОТКЛ",
            "U2 БЛОК",
            "U2 ОТКЛ",
        ]
        for organ_name in toggleable_organs_list:
            # Проверяем, есть ли чекбокс для этого органа в POST
            enabled_organs[organ_name] = (
                request.POST.get(f"organ_enabled_{organ_name}", "off") == "on"
            )

        request.session["enabled_organs"] = enabled_organs

        # Затем собираем все остальные коэффициенты из SETTINGS_CALCULATION_MAP
        for organ_name, organ_data in SETTINGS_CALCULATION_MAP.items():
            if organ_data.get("calculation_factors"):
                for factor_key in organ_data["calculation_factors"].keys():
                    # Получаем значение из POST, если оно есть
                    if factor_key in request.POST:
                        try:
                            value = float(request.POST[factor_key])
                            calculation_factors[factor_key] = value
                        except (ValueError, TypeError):
                            # Если не удалось преобразовать, используем значение по умолчанию
                            default_value = organ_data["calculation_factors"][
                                factor_key
                            ].get("default_value")
                            if default_value is not None:
                                calculation_factors[factor_key] = default_value

        # Логируем выбор ДДТН
        if "load_current" in calculation_factors:
            load_current_value = calculation_factors["load_current"]
            FaultCalculationService._log(
                f"[DEBUG] Пользователь выбрал ДДТН (длительно допустимый рабочий ток): {load_current_value} А"
            )

        FaultCalculationService._log(f"[DEBUG] Сохраненные коэффициенты: {calculation_factors}")
        request.session["calculation_factors"] = calculation_factors
        request.session.modified = True
        messages.success(
            request,
            f"Коэффициенты успешно сохранены. Всего сохранено: {len(calculation_factors)} коэффициентов.",
        )
        return redirect("calculation")

    def toggle_organ(self, request):
        """Переключает состояние органа (включен/выключен) через AJAX."""
        organ_name = request.POST.get("organ_name")
        enabled = request.POST.get("enabled") == "on"

        if not organ_name:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {"success": False, "message": "Не указано название органа"},
                    status=400,
                )
            return redirect("calculation")

        # Получаем текущее состояние органов из сессии
        enabled_organs = request.session.get("enabled_organs", {})
        enabled_organs[organ_name] = enabled
        request.session["enabled_organs"] = enabled_organs
        request.session.modified = True

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": f'Орган {organ_name} {"включен" if enabled else "отключен"}',
                    "organ_name": organ_name,
                    "enabled": enabled,
                }
            )

        return redirect("calculation")

    def calculate_settings(self, request):
        FaultCalculationService._log("Начало расчета")
        half_set1_submodes = request.session.get("half_set1_submodes")
        half_set2_submodes = request.session.get("half_set2_submodes")
        calculation_factors = request.session.get("calculation_factors")
        line_id = request.session.get("line_id", None)

        project_name = request.session.get("pf_project_name")
        line_query = Line.objects.filter(pk=line_id)
        if project_name:
            line_query = line_query.filter(project_name=project_name)
        line = line_query.get()
        protection_half_sets = list(line.protection_half_sets.all())

        # Проверяем наличие полукомплектов защиты
        if len(protection_half_sets) < 2:
            messages.error(
                request,
                f"Для ЛЭП '{line.dispatch_name}' не найдено полукомплектов защиты. "
                f"Найдено: {len(protection_half_sets)}, требуется: 2. "
                f"Пожалуйста, создайте полукомплекты защиты с помощью команды: "
                f"python manage.py create_protection_half_sets_for_all_lines --line-id {line.id}",
            )
            return redirect("calculation")

        half_set1 = protection_half_sets[0]
        half_set2 = protection_half_sets[1]

        # Создаем экземпляр сервиса расчета токов КЗ
        fault_service = FaultCalculationService()

        # Регистрируем расчет
        # Создаем новый CalculationMeta для каждого расчета
        FaultCalculationService._log(f"[DEBUG] ========== Создание нового расчета ==========")
        FaultCalculationService._log(f"[DEBUG] ЛЭП: {line} (ID: {line.id})")
        FaultCalculationService._log(f"[DEBUG] Пользователь: {request.user}")

        # Проверяем, есть ли старые расчеты для этой ЛЭП
        old_calculations = CalculationMeta.objects.filter(line=line).order_by(
            "-calculation_date"
        )
        if old_calculations.exists():
            FaultCalculationService._log(
                f"[DEBUG] Найдено старых расчетов для этой ЛЭП: {old_calculations.count()}"
            )
            FaultCalculationService._log(
                f"[DEBUG] Последний старый расчет: ID={old_calculations.first().id}, Дата={old_calculations.first().calculation_date}"
            )

        calculation_meta = CalculationMeta.objects.create(line=line, user=request.user)
        FaultCalculationService._log(
            f"[DEBUG] ✓ Создан новый расчет: ID={calculation_meta.id}, ЛЭП={line}, Дата={calculation_meta.calculation_date}"
        )
        FaultCalculationService._log(f"[DEBUG] ============================================")

        # Создаем COM-объект PowerFactory
        project_name = request.session.get("pf_project_name")
        app = self.pf_manager.get_application(project_name=project_name)

        # Выполняем расчет токов КЗ на противоположной стороне
        fault_service.perform_fault_calculation(
            app, half_set1, half_set1_submodes, calculation_meta
        )
        fault_service.perform_fault_calculation(
            app, half_set2, half_set2_submodes, calculation_meta
        )

        # Выполняем расчет КЗ на подстанциях ответвлений (для расчета X откл отв)
        # Если у линии есть ответвления, моделируем КЗ на всех подстанциях ответвлений
        if line.branches.filter(is_active=True).exists():
            fault_service.perform_branch_fault_calculation(
                app, half_set1, half_set1_submodes, calculation_meta
            )
            fault_service.perform_branch_fault_calculation(
                app, half_set2, half_set2_submodes, calculation_meta
            )

        # Освобождаем COM-объект
        del app

        # Получаем состояние включения/отключения органов из сессии
        enabled_organs = request.session.get("enabled_organs", {})

        # Выполняем расчет параметров настройки ДФЗ
        calculation_service = SettingsCalculationService(
            calculation_meta, calculation_factors, enabled_organs
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


@require_http_methods(["GET"])
def filter_lines_ajax(request):
    """AJAX endpoint для фильтрации ЛЭП по типу и напряжению."""
    from decimal import Decimal

    line_type_id = request.GET.get("line_type_id")
    voltage = request.GET.get("voltage")

    # Получаем проект из сессии для фильтрации
    project_name = request.GET.get("project_name") or request.session.get(
        "pf_project_name"
    )

    queryset = Line.objects.all()
    if project_name:
        queryset = queryset.filter(project_name=project_name)
    queryset = queryset.order_by("dispatch_name")

    # Фильтруем по типу
    if line_type_id:
        queryset = queryset.filter(line_type_id=line_type_id)

    # Фильтруем по напряжению (если пустое значение - не фильтруем, показываем все)
    if voltage:
        try:
            voltage_decimal = Decimal(voltage)
            queryset = queryset.filter(voltage_level=voltage_decimal)
        except (ValueError, TypeError, Exception):
            pass

    # Формируем список для JSON
    lines = [{"id": line.id, "name": line.dispatch_name} for line in queryset]

    return JsonResponse({"lines": lines})


@require_http_methods(["GET"])
@login_required
def get_line_vt_ajax(request):
    """AJAX endpoint для получения подходящего ТН для выбранной ЛЭП."""
    from core.models import VoltageTransformer

    line_id = request.GET.get("line_id")
    if not line_id:
        return JsonResponse(
            {"success": False, "message": "Не указан ID ЛЭП"}, status=400
        )

    try:
        line = Line.objects.get(pk=line_id)

        # Если у линии уже есть ТН, возвращаем его
        if line.vt:
            return JsonResponse(
                {
                    "success": True,
                    "vt_id": line.vt.id,
                    "vt_name": str(line.vt),
                    "voltage_level": float(line.voltage_level)
                    if line.voltage_level
                    else None,
                }
            )

        # Если у линии есть напряжение, ищем подходящий ТН
        if line.voltage_level:
            line_voltage_int = int(float(line.voltage_level))
            
            # Ищем ТН с точным совпадением по primary_voltage
            # Если найдено несколько, выбираем первый (можно добавить сортировку по ID или типу)
            vt_queryset = VoltageTransformer.objects.filter(
                primary_voltage=line_voltage_int
            ).order_by('id')
            
            # Логируем для отладки
            FaultCalculationService._log(
                f"[DEBUG] Поиск ТН для ЛЭП {line.dispatch_name} (напряжение: {line.voltage_level} кВ, int: {line_voltage_int})"
            )
            FaultCalculationService._log(
                f"[DEBUG] Найдено ТН с primary_voltage={line_voltage_int}: {vt_queryset.count()}"
            )
            
            if vt_queryset.exists():
                vt = vt_queryset.first()
                FaultCalculationService._log(
                    f"[DEBUG] Выбран ТН: {vt} (ID: {vt.id}, primary_voltage: {vt.primary_voltage} кВ)"
                )
                return JsonResponse(
                    {
                        "success": True,
                        "vt_id": vt.id,
                        "vt_name": str(vt),
                        "voltage_level": float(line.voltage_level),
                    }
                )
            else:
                # Логируем, если ТН не найден
                FaultCalculationService._log(
                    f"[WARNING] ТН с primary_voltage={line_voltage_int} кВ не найден для ЛЭП {line.dispatch_name}"
                )
                # Проверяем, какие ТН есть в базе
                all_vts = VoltageTransformer.objects.values_list('primary_voltage', flat=True).distinct()
                FaultCalculationService._log(
                    f"[DEBUG] Доступные напряжения ТН в БД: {sorted(set(all_vts))}"
                )

        return JsonResponse(
            {
                "success": False,
                "message": "Не найдено подходящего ТН для данной ЛЭП",
                "voltage_level": float(line.voltage_level)
                if line.voltage_level
                else None,
            }
        )
    except Line.DoesNotExist:
        return JsonResponse({"success": False, "message": "ЛЭП не найдена"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


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

    # Логируем для диагностики
    FaultCalculationService._log(f"[DEBUG] ========== Отображение результатов расчета ==========")
    FaultCalculationService._log(f"[DEBUG] Запрошен calculation_meta_id: {calculation_meta_id}")
    FaultCalculationService._log(
        f"[DEBUG] Найден CalculationMeta: ID={calculation_meta.id}, ЛЭП={calculation_meta.line}, Дата={calculation_meta.calculation_date}"
    )
    FaultCalculationService._log(f"[DEBUG] Найдено результатов: {results.count()}")

    # Проверяем, есть ли результаты для других расчетов (для диагностики)
    all_results_count = SettingsCalculation.objects.filter(
        calculation_meta__line=calculation_meta.line
    ).count()
    FaultCalculationService._log(
        f"[DEBUG] Всего результатов для ЛЭП {calculation_meta.line}: {all_results_count}"
    )

    # Дополнительная проверка: логируем первые несколько результатов для проверки
    if results.exists():
        FaultCalculationService._log(f"[DEBUG] Первые 3 результата:")
        for i, result in enumerate(results[:3], 1):
            FaultCalculationService._log(
                f"[DEBUG]   {i}. Полукомплект: {result.protection_half_set}, Орган: {result.component}, Значение: {result.result_value}, CalculationMeta ID: {result.calculation_meta.id}"
            )

        # Проверяем, все ли результаты принадлежат запрошенному calculation_meta
        wrong_results = results.exclude(calculation_meta=calculation_meta)
        if wrong_results.exists():
            FaultCalculationService._log(
                f"[ERROR] ОШИБКА: Найдено {wrong_results.count()} результатов с неправильным CalculationMeta!"
            )
            for wrong_result in wrong_results[:3]:
                FaultCalculationService._log(
                    f"[ERROR]   Неправильный результат: ID={wrong_result.id}, CalculationMeta ID={wrong_result.calculation_meta.id} (ожидался {calculation_meta.id})"
                )
        else:
            FaultCalculationService._log(
                f"[DEBUG] ✓ Все результаты принадлежат запрошенному CalculationMeta ID={calculation_meta.id}"
            )

        # Проверяем, все ли органы отображаются
        unique_organs = results.values_list(
            "component__setting_designation", flat=True
        ).distinct()
        FaultCalculationService._log(f"[DEBUG] Уникальных органов в результатах: {len(unique_organs)}")
        FaultCalculationService._log(f"[DEBUG] Список органов: {list(unique_organs)}")

        # Проверяем количество результатов на полукомплект
        for half_set in calculation_meta.line.protection_half_sets.all():
            half_set_results = results.filter(protection_half_set=half_set)
            FaultCalculationService._log(
                f"[DEBUG] Полукомплект {half_set}: {half_set_results.count()} результатов"
            )
    else:
        FaultCalculationService._log(
            f"[WARNING] Нет результатов для calculation_meta_id={calculation_meta_id}"
        )
        # Проверяем, есть ли результаты для других расчетов этой ЛЭП
        other_results = SettingsCalculation.objects.filter(
            calculation_meta__line=calculation_meta.line
        ).exclude(calculation_meta=calculation_meta)
        if other_results.exists():
            FaultCalculationService._log(
                f"[WARNING] Найдено {other_results.count()} результатов для других расчетов этой ЛЭП"
            )
            latest_calc = (
                CalculationMeta.objects.filter(line=calculation_meta.line)
                .order_by("-calculation_date")
                .first()
            )
            if latest_calc:
                FaultCalculationService._log(
                    f"[WARNING] Последний расчет для этой ЛЭП: ID={latest_calc.id}, Дата={latest_calc.calculation_date}"
                )

    return render(
        request,
        "calculation/results.html",
        {"results": results, "calculation_meta": calculation_meta},
    )


def sensitivity_analysis(request, calculation_meta_id):
    calculation_meta = CalculationMeta.objects.get(id=calculation_meta_id)
    sens_analysis = SensitivityAnalysis.objects.filter(
        settings_calculation__calculation_meta=calculation_meta
    ).order_by(
        "settings_calculation__protection_half_set",
        "settings_calculation__component__setting_designation",
        "fault_calculation__fault_type",
        "fault_calculation__fault_location",
    )

    # Логируем для диагностики
    FaultCalculationService._log(
        f"[DEBUG] Отображение анализа чувствительности: ID={calculation_meta_id}, ЛЭП={calculation_meta.line}, Найдено записей: {sens_analysis.count()}"
    )

    # Добавляем пагинацию
    paginator = Paginator(sens_analysis, 15)  # 15 записей на страницу
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Получаем уникальные органы для модального окна (из всех записей, не только текущей страницы)
    unique_components = sens_analysis.values_list(
        "settings_calculation__component__id",
        "settings_calculation__component__setting_designation",
    ).distinct()
    # Получаем уникальные полукомплекты с их строковым представлением
    unique_half_set_ids = sens_analysis.values_list(
        "settings_calculation__protection_half_set__id", flat=True
    ).distinct()
    # Создаем список кортежей (id, строковое представление)
    from core.models import ProtectionHalfSet

    unique_half_sets = [
        (hs.id, str(hs))
        for hs in ProtectionHalfSet.objects.filter(id__in=unique_half_set_ids)
    ]

    return render(
        request,
        "calculation/sensitivity_analysis.html",
        {
            "page_obj": page_obj,
            "calculation_meta": calculation_meta,
            "sens_analysis": sens_analysis,  # Оставляем для обратной совместимости
            "unique_components": unique_components,
            "unique_half_sets": unique_half_sets,
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
    response[
        "Content-Disposition"
    ] = f'attachment; filename="sensitivity_analysis_{calculation_meta.id}.xlsx"'
    wb.save(response)

    return response


def export_calculation_results(request, calculation_meta_id):
    calculation_meta = CalculationMeta.objects.get(id=calculation_meta_id)
    calculations = SettingsCalculation.objects.filter(calculation_meta=calculation_meta).order_by("protection_half_set", "component__setting_designation")
    
    # Логируем для диагностики
    FaultCalculationService._log(f"[DEBUG] ========== Экспорт результатов расчета ==========")
    FaultCalculationService._log(f"[DEBUG] Запрошен calculation_meta_id: {calculation_meta_id}")
    FaultCalculationService._log(f"[DEBUG] Найдено результатов: {calculations.count()}")
    
    # Проверяем наличие U2 БЛОК и U2 ОТКЛ
    u2_results = calculations.filter(component__setting_designation__in=["U2 БЛОК", "U2 ОТКЛ"])
    FaultCalculationService._log(f"[DEBUG] Найдено результатов U2: {u2_results.count()}")
    for u2_result in u2_results:
        FaultCalculationService._log(f"[DEBUG]   U2 результат: {u2_result.component.setting_designation}, Полукомплект: {u2_result.protection_half_set}, Значение: {u2_result.result_value}, Primary: {u2_result.primary_value}, Secondary: {u2_result.secondary_value}")

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

        # Используем primary_value если доступно, иначе result_value
        primary_value = calculation.primary_value if calculation.primary_value is not None else calculation.result_value
        secondary_value = calculation.secondary_value if calculation.secondary_value is not None else None

        ws.cell(row=row_num, column=1, value=str(calculation.protection_half_set))
        ws.cell(row=row_num, column=2, value=str(calculation.component))
        ws.cell(row=row_num, column=3, value=coefficients)
        ws.cell(row=row_num, column=4, value=primary_value)
        ws.cell(row=row_num, column=5, value=secondary_value if secondary_value is not None else "")

    # Создаем HTTP-ответ с файлом Excel
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response[
        "Content-Disposition"
    ] = f'attachment; filename="calculation_results_{calculation_meta.id}.xlsx"'

    wb.save(response)
    return response


@require_http_methods(["GET"])
@login_required
def get_available_projects_ajax(request):
    """
    AJAX endpoint для получения списка доступных проектов PowerFactory.
    """
    try:
        pf_manager = PowerFactoryManager()
        FaultCalculationService._log(f"[DEBUG] get_available_projects_ajax: начало запроса")
        projects = pf_manager.get_available_projects()
        FaultCalculationService._log(
            f"[DEBUG] get_available_projects_ajax: получено проектов: {len(projects) if projects else 0}"
        )

        # Получаем текущий выбранный проект из сессии
        current_project = request.session.get("pf_project_name")
        FaultCalculationService._log(
            f"[DEBUG] get_available_projects_ajax: текущий проект из сессии: {current_project}"
        )

        # Проверяем доступность текущего проекта
        project_status = None
        if current_project:
            try:
                project_status = pf_manager.check_project_available(current_project)
                FaultCalculationService._log(
                    f"[DEBUG] get_available_projects_ajax: статус проекта '{current_project}': {project_status}"
                )
            except Exception as e:
                FaultCalculationService._log(
                    f"[DEBUG] get_available_projects_ajax: ошибка при проверке статуса проекта: {e}"
                )
                project_status = None

        response_data = {
            "projects": projects,
            "current_project": current_project,
            "project_available": project_status,  # True/False/None
        }
        FaultCalculationService._log(f"[DEBUG] get_available_projects_ajax: отправка ответа: {response_data}")
        return JsonResponse(response_data)
    except ModuleNotFoundError as e:
        # PowerFactory не установлен или недоступен
        return JsonResponse(
            {
                "error": "PowerFactory недоступен. Убедитесь, что PowerFactory установлен и запущен.",
                "error_type": "ModuleNotFoundError",
                "projects": [],
                "current_project": None,
                "project_available": None,
            },
            status=500,
        )
    except Exception as e:
        # Другие ошибки
        import traceback

        error_trace = traceback.format_exc()
        FaultCalculationService._log(f"Ошибка при получении проектов PowerFactory: {error_trace}")
        return JsonResponse(
            {
                "error": str(e),
                "error_type": type(e).__name__,
                "projects": [],
                "current_project": None,
                "project_available": None,
            },
            status=500,
        )
