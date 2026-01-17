from django.apps import AppConfig


class CalculationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "calculation"

    def ready(self):
        """
        Вызывается при запуске Django приложения.
        Очищает файл логов при старте веб-приложения.
        """
        try:
            from calculation.services.fault_calculation_service import FaultCalculationService
            # Очищаем файл логов при запуске приложения
            try:
                with open(FaultCalculationService.LOG_FILE_PATH, 'w', encoding='utf-8') as f:
                    pass  # Просто очищаем файл
                # Устанавливаем флаг, что файл уже инициализирован
                FaultCalculationService._log_file_initialized = True
                # Сбрасываем ID последнего расчета
                FaultCalculationService._last_calculation_meta_id = None
            except Exception as e:
                print(f"[ERROR] Не удалось очистить файл логов при запуске приложения: {e}")
        except ImportError:
            # Если FaultCalculationService недоступен, ничего не делаем
            pass
