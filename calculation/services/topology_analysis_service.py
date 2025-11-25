from typing import Dict, List

from core.models import ProtectionHalfSet

from .powerfactory_locator import get_pf_line, get_pf_substation


class TopologyAnalysisService:

    def __init__(
        self,
        protection_half_set: ProtectionHalfSet,
    ):
        self.half_set = protection_half_set

    def get_half_set_topology(self, app):
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
        lines = app.GetCalcRelevantObjects('*.ElmBranch')
        for line in lines:
            if line != pf_protected_line:
                line_terminals = line.GetConnectedElements()
                for terminal in line_terminals:
                    if (
                        terminal.GetParent() == pf_substation
                        and terminal.GetUnom() == voltage_level
                    ):
                        line_dict = {
                            'type': 'ЛЭП',
                            'full_name': line.GetFullName(),
                            'loc_name': line.GetAttribute('loc_name')
                        }
                        substation_lines.append(line_dict)
        return substation_lines

    @staticmethod
    def _get_substation_autotransformers(
        pf_substation, voltage_level
    ) -> List[Dict[str, str]]:
        substation_autotransformers = pf_substation.GetContents('*.ElmTr3')
        valid_autotransformers = []
        for autotransformer in substation_autotransformers:
            autotransformer_high_voltage = (
                autotransformer.GetAttribute('bushv').GetUnom()
            )
            if autotransformer_high_voltage == voltage_level:
                autotransformer_dict = {
                    'type': 'АТ',
                    'full_name': autotransformer.GetFullName(),
                    'loc_name': autotransformer.GetAttribute('loc_name')
                }
                valid_autotransformers.append(autotransformer_dict)
        return valid_autotransformers