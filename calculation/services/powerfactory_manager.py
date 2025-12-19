import sys


class PowerFactoryManager:

    POWERFACTORY_PATH: str = (
        r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP3\Python\3.8"
    )
    PROJECT_NAME: str = "ОДУ Сибири 1.0"

    def __init__(self):
        # Добавляем путь только если его еще нет в sys.path
        if self.POWERFACTORY_PATH not in sys.path:
            sys.path.append(self.POWERFACTORY_PATH)

    def get_application(self):
        # Пытаемся импортировать модуль PowerFactory
        try:
            import powerfactory  # type: ignore
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "Сервер PowerFactory недоступен. "
                "Убедитесь, что PowerFactory установлен и запущен."
            )

        app = powerfactory.GetApplication()

        # Проверяем, что приложение успешно получено
        if app is None:
            raise RuntimeError(
                "Не удалось получить приложение PowerFactory. "
                "Убедитесь, что PowerFactory запущен."
            )

        # Вспомогательная функция: вернуть список доступных проектов
        def get_available_projects():
            available_projects = []
            try:
                projects = app.GetProjects()
                if projects:
                    for proj in projects:
                        try:
                            name = proj.GetAttribute("loc_name")
                            if name:
                                available_projects.append(name)
                        except Exception:
                            pass
            except Exception:
                pass
            return available_projects

        # Смотрим, какой проект сейчас активен
        active_project = app.GetActiveProject()
        active_name = None
        if active_project:
            try:
                active_name = active_project.GetAttribute("loc_name")
            except Exception:
                active_name = None

        # 1. Если уже активен нужный проект — просто возвращаем app
        if active_name == self.PROJECT_NAME:
            return app

        # 2. Если активен другой проект — не пытаемся переключать, просим пользователя
        if active_name and active_name != self.PROJECT_NAME:
            available = get_available_projects()
            msg = (
                f"В PowerFactory уже открыт проект '{active_name}'.\n"
                f"Пожалуйста, вручную откройте проект '{self.PROJECT_NAME}' "
                f"в интерфейсе PowerFactory и повторите запуск команды."
            )
            if available:
                msg += "\nДоступные проекты: " + ", ".join(available)
            raise RuntimeError(msg)

        # 3. Если нет активного проекта — пробуем активировать нужный
        app.ActivateProject(self.PROJECT_NAME)
        active_after = app.GetActiveProject()
        if active_after:
            try:
                after_name = active_after.GetAttribute("loc_name")
                if after_name == self.PROJECT_NAME:
                    return app
            except Exception:
                pass

        # 4. Не удалось активировать даже при отсутствии активного проекта
        available = get_available_projects()
        msg = f'Не удалось активировать проект "{self.PROJECT_NAME}".'
        if available:
            msg += " Доступные проекты: " + ", ".join(available)
        else:
            msg += " Не удалось получить список доступных проектов."
        raise RuntimeError(msg)
