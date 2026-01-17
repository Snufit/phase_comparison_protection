"""
Сервис для синхронизации проекта PowerFactory с базой данных.

При выборе проекта выполняет:
1. Импорт всех линий из PowerFactory
2. Импорт всех подстанций из PowerFactory
3. Импорт ответвлений для линий
4. Создание полукомплектов защиты для всех линий
5. Анализ топологии для всех полукомплектов
"""

from decimal import Decimal
import math
from typing import Dict, List, Optional

from core.models import (
    Line,
    LineType,
    LineBranch,
    Substation,
    ProtectionHalfSet,
    ProtectionDevice,
)
from calculation.services.powerfactory_manager import PowerFactoryManager
from calculation.services.powerfactory_locator import (
    get_line_type,
    _has_branches,
    _get_line_end_substations,
    _get_main_substations_with_voltage,
    get_pf_line,
)
from calculation.services.topology_analysis_service import TopologyAnalysisService
from calculation.services.fault_calculation_service import FaultCalculationService


class ProjectSyncService:
    """Сервис для синхронизации проекта PowerFactory с БД."""

    def __init__(self, project_name: str, default_device_model: str = "ШЭ 2607 081"):
        """
        Инициализация сервиса.

        Args:
            project_name: Имя проекта PowerFactory для синхронизации
            default_device_model: Модель устройства РЗА по умолчанию
        """
        self.project_name = project_name
        self.default_device_model = default_device_model
        self.pf_manager = PowerFactoryManager()
        self.app = None

    def needs_sync(self) -> bool:
        """
        Проверяет, нужна ли синхронизация проекта.

        Returns:
            True если нужно синхронизировать, False если данные уже есть
        """
        # Проверяем наличие данных в БД для этого проекта
        lines_count = (
            Line.objects.filter(
                project_name=self.project_name, pf_name__isnull=False)
            .exclude(pf_name="")
            .count()
        )
        substations_count = Substation.objects.filter(
            project_name=self.project_name
        ).count()

        # Если есть хотя бы минимальные данные для этого проекта, считаем что синхронизация уже была
        needs = lines_count == 0 or substations_count == 0
        FaultCalculationService._log(
            f"[DEBUG] needs_sync для проекта '{self.project_name}': lines={lines_count}, substations={substations_count}, needs={needs}"
        )
        return needs

    def sync_project(self, force_full: bool = False) -> Dict[str, any]:
        """
        Выполняет синхронизацию проекта с БД.
        Если данные уже есть, выполняет только обновление.

        Args:
            force_full: Если True, выполняет полную синхронизацию даже если данные есть

        Returns:
            Dict с результатами синхронизации (статистика)
        """
        results = {
            "lines": {"created": 0, "updated": 0, "errors": 0},
            "substations": {"created": 0, "updated": 0, "errors": 0},
            "branches": {"filled": 0, "errors": 0},
            "half_sets": {"created": 0, "errors": 0},
            "topology": {"analyzed": 0, "errors": 0},
            "skipped": False,
        }

        # Проверяем, нужна ли синхронизация
        needs_full_sync = self.needs_sync()
        if not force_full and not needs_full_sync:
            results["skipped"] = True
            results[
                "message"
            ] = "Данные проекта уже синхронизированы. Используются существующие данные."
            return results

        try:
            # Подключаемся к PowerFactory с указанным проектом
            self.app = self.pf_manager.get_application(
                project_name=self.project_name)

            # Если данных нет, создаем новые (update_only=False)
            # Если данные есть, только обновляем существующие (update_only=True)
            update_only = not needs_full_sync and not force_full
            FaultCalculationService._log(
                f"[DEBUG] sync_project: needs_full_sync={needs_full_sync}, force_full={force_full}, update_only={update_only}"
            )

            # 1. Импорт линий
            results["lines"] = self._import_lines(update_only=update_only)

            # 2. Импорт подстанций
            results["substations"] = self._import_substations(
                update_only=update_only)

            # 3. Импорт ответвлений (только для новых линий или при полной синхронизации)
            if force_full or results["lines"]["created"] > 0:
                results["branches"] = self._import_branches()

            # 4. Создание полукомплектов защиты (только для новых линий)
            if force_full or results["lines"]["created"] > 0:
                results["half_sets"] = self._create_protection_half_sets()

            # 5. Анализ топологии (только для новых полукомплектов или при полной синхронизации)
            if force_full or results["half_sets"]["created"] > 0:
                results["topology"] = self._analyze_topology(
                    force_refresh=force_full)

            # Очищаем thread-local app после синхронизации, чтобы следующий запрос создал новый
            if hasattr(self.pf_manager._thread_local, "app"):
                self.pf_manager._thread_local.app = None

        except Exception as e:
            results["error"] = str(e)
            # Очищаем thread-local app даже при ошибке
            if hasattr(self.pf_manager._thread_local, "app"):
                self.pf_manager._thread_local.app = None
            raise

        return results

    def _import_lines(self, update_only: bool = False) -> Dict[str, int]:
        """Импортирует все линии из PowerFactory."""
        stats = {"created": 0, "updated": 0, "errors": 0}

        try:
            pf_lines = self.app.GetCalcRelevantObjects("*.ElmBranch") or []

            for index, pf_line in enumerate(pf_lines):
                try:
                    pf_name = pf_line.GetAttribute("loc_name")
                    if not pf_name:
                        continue

                    # Получаем данные линии
                    voltage_level = None
                    try:
                        line_terminals = pf_line.GetConnectedElements()
                        if line_terminals:
                            voltage_raw = line_terminals[0].GetUnom()
                            if voltage_raw is not None:
                                voltage_level = Decimal(
                                    str(round(voltage_raw, 2)))
                    except Exception:
                        pass

                    length = None
                    try:
                        length_raw = pf_line.GetAttribute("length")
                        if length_raw is not None:
                            length = Decimal(str(round(length_raw, 2)))
                    except Exception:
                        pass

                    # Получаем сопротивления
                    r1 = self._get_decimal_attribute(pf_line, "R1")
                    r0 = self._get_decimal_attribute(pf_line, "R0")
                    x1 = self._get_decimal_attribute(pf_line, "X1")
                    x0 = self._get_decimal_attribute(pf_line, "X0")

                    # Вычисляем Z1 и Z0
                    z1 = None
                    if r1 is not None and x1 is not None:
                        z1_value = math.sqrt(float(r1) ** 2 + float(x1) ** 2)
                        z1 = Decimal(str(round(z1_value, 2)))

                    z0 = None
                    if r0 is not None and x0 is not None:
                        z0_value = math.sqrt(float(r0) ** 2 + float(x0) ** 2)
                        z0 = Decimal(str(round(z0_value, 2)))

                    # Определяем тип ЛЭП
                    line_type_str = None
                    try:
                        line_type_str = get_line_type(self.app, pf_line)
                    except Exception:
                        pass

                    line_type_obj = None
                    if line_type_str:
                        line_type_obj, _ = LineType.objects.get_or_create(
                            type_code=line_type_str
                        )

                    # Проверяем ответвления
                    has_branches = False
                    branch_substations = []
                    if line_type_str and (
                        "ответвлением" in line_type_str
                        or "ответвлениями" in line_type_str
                    ):
                        try:
                            branch_substations = _has_branches(
                                self.app,
                                pf_line,
                                return_branch_substations=True,
                                check_substations=True,
                            )
                            has_branches = len(branch_substations) > 0
                        except Exception:
                            pass

                    # Проверяем, существует ли линия для этого проекта
                    try:
                        existing_line = Line.objects.get(
                            pf_name=pf_name, project_name=self.project_name
                        )
                        created = False
                    except Line.DoesNotExist:
                        # Создаем новую линию только если не update_only
                        if update_only:
                            FaultCalculationService._log(
                                f"[DEBUG] Пропуск создания линии '{pf_name}' (update_only=True)"
                            )
                            continue
                        FaultCalculationService._log(
                            f"[DEBUG] Создание новой линии '{pf_name}' для проекта '{self.project_name}'"
                        )
                        try:
                            existing_line = Line.objects.create(
                                dispatch_name=pf_name,
                                pf_name=pf_name,
                                project_name=self.project_name,
                                index_pf=index,
                                voltage_level=voltage_level or Decimal("0.00"),
                                length=length or Decimal("0.00"),
                                r1=r1,
                                r0=r0,
                                x1=x1,
                                x0=x0,
                                z1=z1,
                                z0=z0,
                                line_type=line_type_obj,
                            )
                            created = True
                            FaultCalculationService._log(
                                f"[DEBUG] Линия '{pf_name}' успешно создана (ID: {existing_line.id})"
                            )
                        except Exception as create_error:
                            FaultCalculationService._log(
                                f"[DEBUG] Ошибка при создании линии '{pf_name}': {create_error}"
                            )
                            stats["errors"] += 1
                            continue
                    except Line.MultipleObjectsReturned:
                        # Если найдено несколько линий, берем первую
                        existing_line = Line.objects.filter(
                            pf_name=pf_name, project_name=self.project_name
                        ).first()
                        created = False

                    if not created:
                        # Обновляем существующую
                        existing_line.index_pf = index
                        existing_line.project_name = (
                            self.project_name
                        )  # Обновляем проект
                        if voltage_level is not None:
                            existing_line.voltage_level = voltage_level
                        if length is not None:
                            existing_line.length = length
                        if r1 is not None:
                            existing_line.r1 = r1
                        if r0 is not None:
                            existing_line.r0 = r0
                        if x1 is not None:
                            existing_line.x1 = x1
                        if x0 is not None:
                            existing_line.x0 = x0
                        if z1 is not None:
                            existing_line.z1 = z1
                        if z0 is not None:
                            existing_line.z0 = z0
                        if line_type_obj is not None:
                            existing_line.line_type = line_type_obj
                        existing_line.save()
                        stats["updated"] += 1
                    else:
                        stats["created"] += 1

                    # Создаем LineBranch для линий с ответвлениями
                    if has_branches:
                        existing_branches = LineBranch.objects.filter(
                            line=existing_line
                        )
                        if existing_branches.count() < len(branch_substations):
                            for _ in range(
                                len(branch_substations) -
                                    existing_branches.count()
                            ):
                                LineBranch.objects.create(
                                    line=existing_line,
                                    pf_name_line=pf_name,
                                    substation=None,
                                    is_active=True,
                                )

                except Exception as e:
                    stats["errors"] += 1
                    continue

        except Exception as e:
            stats["errors"] += 1

        return stats

    def _import_substations(self, update_only: bool = False) -> Dict[str, int]:
        """Импортирует все подстанции из PowerFactory."""
        stats = {"created": 0, "updated": 0, "errors": 0}

        try:
            pf_substations = self.app.GetCalcRelevantObjects(
                "*.ElmSubstat") or []

            for pf_substation in pf_substations:
                try:
                    pf_name = pf_substation.GetAttribute("loc_name")
                    if not pf_name:
                        continue

                    try:
                        substation = Substation.objects.get(
                            pf_name=pf_name, project_name=self.project_name
                        )
                        created = False
                    except Substation.DoesNotExist:
                        # Создаем новую подстанцию только если не update_only
                        if update_only:
                            continue
                        substation = Substation.objects.create(
                            pf_name=pf_name, project_name=self.project_name
                        )
                        created = True
                    else:
                        # Обновляем project_name для существующей подстанции
                        substation.project_name = self.project_name
                        substation.save()

                    if created:
                        stats["created"] += 1
                    else:
                        stats["updated"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    continue

        except Exception as e:
            stats["errors"] += 1

        return stats

    def _import_branches(self) -> Dict[str, int]:
        """Импортирует ответвления для линий."""
        stats = {"filled": 0, "errors": 0}

        try:
            unique_lines = Line.objects.filter(
                project_name=self.project_name, branches__substation__isnull=True
            ).distinct()

            for line in unique_lines:
                try:
                    if not line.pf_name:
                        continue

                    pf_line = get_pf_line(self.app, line.pf_name)
                    if not pf_line:
                        continue

                    # Определяем подстанции ответвлений
                    all_substations = _get_line_end_substations(
                        pf_line, self.app)
                    main_substations = _get_main_substations_with_voltage(
                        pf_line, self.app
                    )

                    main_substations_set = {
                        (sub["name"], sub["voltage_kv"]) for sub in main_substations
                    }
                    all_substations_set = {
                        (sub["name"], sub["voltage_kv"]) for sub in all_substations
                    }

                    branch_substations_keys = all_substations_set - main_substations_set

                    line_branches = LineBranch.objects.filter(
                        line=line, substation__isnull=True
                    )

                    branch_substations_list = [
                        sub
                        for sub in all_substations
                        if (sub["name"], sub["voltage_kv"]) in branch_substations_keys
                    ]

                    # Создаем недостающие LineBranch
                    if len(branch_substations_list) > line_branches.count():
                        for _ in range(
                            len(branch_substations_list) -
                                line_branches.count()
                        ):
                            LineBranch.objects.create(
                                line=line,
                                pf_name_line=line.pf_name,
                                substation=None,
                                is_active=True,
                            )
                        line_branches = LineBranch.objects.filter(
                            line=line, substation__isnull=True
                        )

                    # Заполняем подстанции
                    for i, line_branch in enumerate(line_branches):
                        if i < len(branch_substations_list):
                            substation_data = branch_substations_list[i]
                            substation_name = substation_data["name"]

                            substation, _ = Substation.objects.get_or_create(
                                pf_name=substation_name,
                                project_name=self.project_name,
                                defaults={"pf_name": substation_name},
                            )

                            line_branch.substation = substation
                            line_branch.pf_name_substation = substation_name
                            line_branch.save()

                            stats["filled"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    continue

        except Exception as e:
            stats["errors"] += 1

        return stats

    def _create_protection_half_sets(self) -> Dict[str, int]:
        """Создает полукомплекты защиты для всех линий."""
        stats = {"created": 0, "errors": 0}

        try:
            # Получаем устройство РЗА
            try:
                protection_device = ProtectionDevice.objects.get(
                    device_model=self.default_device_model
                )
            except ProtectionDevice.DoesNotExist:
                stats["errors"] += 1
                return stats

            # Находим все линии с pf_name для этого проекта
            lines = Line.objects.filter(
                project_name=self.project_name, pf_name__isnull=False
            ).exclude(pf_name="")

            for line in lines:
                try:
                    # Определяем основные подстанции
                    pf_line = get_pf_line(self.app, line.pf_name)
                    if not pf_line:
                        continue

                    main_substations = _get_main_substations_with_voltage(
                        pf_line, self.app
                    )

                    # Если подстанций нет, пропускаем линию
                    if not main_substations:
                        continue

                    # Убираем дубликаты подстанций (по имени)
                    unique_substations = {}
                    for substation_data in main_substations:
                        substation_name = substation_data["name"]
                        if substation_name not in unique_substations:
                            unique_substations[substation_name] = substation_data

                    # Создаем полукомплекты для каждой уникальной подстанции
                    # Для ДФЗ обычно нужно 2 полукомплекта, но если подстанция одна - создаем один
                    for substation_name, substation_data in unique_substations.items():
                        # Находим или создаем подстанцию для этого проекта
                        substation, _ = Substation.objects.get_or_create(
                            pf_name=substation_name,
                            project_name=self.project_name,
                            defaults={"pf_name": substation_name},
                        )

                        # Проверяем, существует ли уже полукомплект
                        existing = ProtectionHalfSet.objects.filter(
                            line=line, substation=substation
                        ).exists()

                        if not existing:
                            ProtectionHalfSet.objects.create(
                                line=line,
                                substation=substation,
                                protection_device=protection_device,
                            )
                            stats["created"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    continue

        except Exception as e:
            stats["errors"] += 1

        return stats

    def _analyze_topology(self, force_refresh: bool = False) -> Dict[str, int]:
        """
        Анализирует топологию для всех полукомплектов.

        Args:
            force_refresh: Если True, обновляет топологию даже если она уже есть в БД
        """
        stats = {"analyzed": 0, "errors": 0}

        try:
            half_sets = ProtectionHalfSet.objects.all().select_related(
                "line", "substation", "protection_device"
            )

            for half_set in half_sets:
                try:
                    topology_service = TopologyAnalysisService(half_set)
                    topology_service.get_half_set_topology(
                        app=self.app, force_refresh=force_refresh
                    )
                    stats["analyzed"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    continue

        except Exception as e:
            stats["errors"] += 1

        return stats

    def _get_decimal_attribute(self, obj, attr_name: str) -> Optional[Decimal]:
        """Получает атрибут объекта как Decimal."""
        try:
            value = obj.GetAttribute(attr_name)
            if value is not None:
                return Decimal(str(round(value, 2)))
        except Exception:
            pass
        return None
