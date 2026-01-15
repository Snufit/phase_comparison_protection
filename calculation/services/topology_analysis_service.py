import hashlib
import json
from typing import Any, Dict, List, Optional

from django.utils import timezone
from core.models import ProtectionHalfSet, HalfSetTopology

from .powerfactory_locator import get_pf_line, get_pf_substation


class TopologyAnalysisService:
    def __init__(
        self,
        protection_half_set: ProtectionHalfSet,  # Вход: полукомплект защиты
    ):
        self.half_set = (
            protection_half_set  # # Сохраняем объект для дальнейшего использования
        )

    def get_half_set_topology(
        self, app: Optional[Any] = None, force_refresh: bool = False
    ) -> List[Dict[str, str]]:
        """
        Получает топологию из БД или PowerFactory.

        Args:
            app: COM-объект PowerFactory (опционально, если есть кэш)
            force_refresh: Принудительное обновление из PowerFactory

        Returns:
            List[Dict] - список элементов топологии
        """
        # Пытаемся получить из БД
        if not force_refresh:
            try:
                topology_obj = HalfSetTopology.objects.get(
                    protection_half_set=self.half_set
                )

                # Проверяем актуальность (например, не старше 30 дней)
                days_old = (timezone.now() - topology_obj.last_updated).days
                if days_old < 30:  # Настраиваемый параметр
                    return topology_obj.topology_data

            except HalfSetTopology.DoesNotExist:
                pass

        # Если нет в БД или устарела - получаем из PowerFactory
        if app is None:
            from calculation.services.powerfactory_manager import PowerFactoryManager

            pf_manager = PowerFactoryManager()
            app = pf_manager.get_application()

        # Получаем топологию из PowerFactory
        topology = self._fetch_topology_from_pf(app)

        # Сохраняем в БД
        self._save_topology_to_db(topology)

        return topology

    def _fetch_topology_from_pf(self, app) -> List[Dict[str, str]]:
        """Получает топологию из PowerFactory (старая логика)."""
        # Определяем ЛЭП и ПС полукомплекта
        line_pf_name = self.half_set.line.pf_name
        substation_pf_name = self.half_set.substation.pf_name

        # Находим ЛЭП и ПС в модели PowerFactory
        pf_line = get_pf_line(app, line_pf_name)
        pf_substation = get_pf_substation(app, substation_pf_name)

        # Определяем напряжение ЛЭП
        voltage_level = self._get_pf_line_voltage_level(pf_line)

        # Определяем смежные ЛЭП и АТ
        substation_lines = self._get_substation_lines(
            app, pf_line, pf_substation, voltage_level
        )
        substation_autotransformers = self._get_substation_autotransformers(
            pf_substation, voltage_level
        )
        half_set_topology = substation_lines + substation_autotransformers

        return half_set_topology

    def _save_topology_to_db(self, topology: List[Dict[str, str]]) -> None:
        """Сохраняет топологию в БД."""
        # Вычисляем хэш для проверки изменений
        topology_json = json.dumps(topology, sort_keys=True)
        topology_hash = hashlib.md5(topology_json.encode()).hexdigest()

        # Получаем напряжение
        voltage_level = None
        if self.half_set.line.voltage_level:
            voltage_level = self.half_set.line.voltage_level

        # Создаем или обновляем запись
        HalfSetTopology.objects.update_or_create(
            protection_half_set=self.half_set,
            defaults={
                "topology_data": topology,
                "topology_hash": topology_hash,
                "voltage_level": voltage_level,
            },
        )

    @staticmethod
    def _get_pf_line_voltage_level(pf_line) -> float:
        line_terminals = pf_line.GetConnectedElements()
        voltage_level = line_terminals[0].GetUnom()
        return voltage_level

    @staticmethod
    def _get_substation_lines(
        app, pf_protected_line, pf_substation, voltage_level
    ) -> List[Dict[str, str]]:
        substation_lines = []
        lines = app.GetCalcRelevantObjects("*.ElmBranch")
        for line in lines:
            if line != pf_protected_line:
                line_terminals = line.GetConnectedElements()
                for terminal in line_terminals:
                    if (
                        terminal.GetParent() == pf_substation
                        and terminal.GetUnom() == voltage_level
                    ):
                        line_dict = {
                            "type": "ЛЭП",
                            "full_name": line.GetFullName(),
                            "loc_name": line.GetAttribute("loc_name"),
                        }
                        substation_lines.append(line_dict)
        return substation_lines

    @staticmethod
    def _get_substation_autotransformers(
        pf_substation, voltage_level
    ) -> List[Dict[str, str]]:
        substation_autotransformers = pf_substation.GetContents("*.ElmTr3")
        valid_autotransformers = []
        for autotransformer in substation_autotransformers:
            autotransformer_high_voltage = autotransformer.GetAttribute(
                "bushv"
            ).GetUnom()
            if autotransformer_high_voltage == voltage_level:
                autotransformer_dict = {
                    "type": "АТ",
                    "full_name": autotransformer.GetFullName(),
                    "loc_name": autotransformer.GetAttribute("loc_name"),
                }
                valid_autotransformers.append(autotransformer_dict)
        return valid_autotransformers
