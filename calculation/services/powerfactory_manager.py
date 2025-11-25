import sys


class PowerFactoryManager:

    POWERFACTORY_PATH: str = (
        r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP3\Python\3.8"
    )
    PROJECT_NAME: str = "NewHope"

    def __init__(self):
        # Добавляем путь только если его еще нет в sys.path
        if self.POWERFACTORY_PATH not in sys.path:
            sys.path.append(self.POWERFACTORY_PATH)

    def get_application(self):
        try:
            import powerfactory  # type: ignore
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "Сервер PowerFactory недоступен, пожалуйста, обратитесь к администратору."
            )

        app = powerfactory.GetApplication()

        # Проверяем, что приложение успешно получено
        if app is None:
            raise RuntimeError(
                "Не удалось получить приложение PowerFactory. Убедитесь, что PowerFactory запущен."
            )

        # Активируем проект и проверяем результат
        result = app.ActivateProject(self.PROJECT_NAME)
        if not result:
            raise RuntimeError(
                f'Не удалось активировать проект "{self.PROJECT_NAME}". '
                f"Убедитесь, что проект существует и доступен."
            )

        return app
