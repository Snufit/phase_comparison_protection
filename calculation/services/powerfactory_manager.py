import sys
import threading
import time
from functools import wraps

try:
    import pythoncom  # type: ignore[import-untyped]
except ImportError:
    pythoncom = None


def handle_threading_error(func):
    """
    Декоратор для обработки ошибок многопоточности PowerFactory.
    Автоматически пересоздает app при ошибке "can't be used from other threads".
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        max_retries = 2
        for attempt in range(max_retries):
            try:
                return func(self, *args, **kwargs)
            except RuntimeError as e:
                if "can't be used from other threads" in str(e) and attempt < max_retries - 1:
                    # Очищаем thread-local app и пробуем снова
                    if hasattr(PowerFactoryManager._thread_local, 'app'):
                        PowerFactoryManager._thread_local.app = None
                    continue
                raise
    return wrapper


class PowerFactoryManager:

    POWERFACTORY_PATH: str = (
        r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP3\Python\3.8"
    )
    PROJECT_NAME: str = "ОДУ Сибири 1.0"

    # Thread-local storage для хранения экземпляра app в каждом потоке
    _thread_local = threading.local()

    # Кэш для списка проектов (общий для всех потоков)
    _projects_cache = None
    _projects_cache_time = 0
    # Время жизни кэша в секундах (увеличено для уменьшения частоты запросов)
    _cache_ttl = 60

    def __init__(self):
        # Добавляем путь только если его еще нет в sys.path
        if self.POWERFACTORY_PATH not in sys.path:
            sys.path.append(self.POWERFACTORY_PATH)

        # Предупреждение о многопоточности (только при первом создании)
        if not hasattr(PowerFactoryManager, '_threading_warning_shown'):
            import threading
            active_threads = threading.active_count()
            if active_threads > 1:
                print(f"[WARNING] Обнаружено {active_threads} активных потоков. "
                      f"PowerFactory требует однопоточный режим. "
                      f"Запустите сервер с флагом --nothreading: "
                      f"python manage.py runserver --nothreading")
            PowerFactoryManager._threading_warning_shown = True

    @handle_threading_error
    def get_application(self, project_name=None):
        """
        Получает приложение PowerFactory с активацией проекта.

        Args:
            project_name: Имя проекта для активации.
                         Если None, используется PROJECT_NAME по умолчанию.

        Returns:
            app: COM-объект PowerFactory
        """
        # Используем переданное имя проекта или значение по умолчанию
        target_project = project_name or self.PROJECT_NAME

        # Инициализируем COM для текущего потока в STA режиме (если еще не инициализирован)
        # PowerFactory требует STA (Single Threaded Apartment) модель
        if pythoncom is not None:
            try:
                # Используем CoInitializeEx с COINIT_APARTMENTTHREADED для STA модели
                # COINIT_APARTMENTTHREADED = 0x2
                apartment_threaded = getattr(
                    pythoncom, 'COINIT_APARTMENTTHREADED', 0x2)
                pythoncom.CoInitializeEx(apartment_threaded)
            except Exception:
                # COM уже инициализирован в этом потоке - это нормально
                # Продолжаем работу, так как COM может быть уже инициализирован
                pass

        # Проверяем, есть ли уже инициализированный app для этого потока
        # ВАЖНО: не используем кэшированный app без проверки, так как он может быть из другого потока
        # Всегда создаем новый app для каждого запроса, чтобы избежать проблем с многопоточностью
        # Thread-local storage может не работать правильно с PowerFactory COM объектами
                self._thread_local.app = None

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
            projects_set = set()
            try:
                # Метод 1: Получаем проекты текущего пользователя
                current_user = app.GetCurrentUser()
                if current_user:
                    projects = current_user.GetContents("*.IntPrj")
                    if projects:
                        for proj in projects:
                            try:
                                name = proj.GetAttribute("loc_name")
                                if name:
                                    projects_set.add(name)
                            except Exception:
                                pass

                # Метод 2: Получаем проекты всех пользователей
                users = app.GetAllUsers()
                if users:
                    for user in users:
                        try:
                            projects = user.GetContents("*.IntPrj")
                            if projects:
                                for proj in projects:
                                    try:
                                        name = proj.GetAttribute("loc_name")
                                        if name:
                                            projects_set.add(name)
                                    except Exception:
                                        pass
                        except Exception:
                            pass
            except Exception:
                pass
            return sorted(list(projects_set))

        # Вспомогательная функция для безопасного получения активного проекта
        def safe_get_active_project(app_instance):
            """Безопасно получает активный проект с обработкой ошибок многопоточности."""
            try:
                return app_instance.GetActiveProject()
            except RuntimeError as e:
                if "can't be used from other threads" in str(e):
                    # Ошибка многопоточности - возвращаем None, чтобы пересоздать app
                    return None
                raise
            except Exception as e:
                raise RuntimeError(
                    f"Ошибка при получении активного проекта PowerFactory: {e}. "
                    "Убедитесь, что PowerFactory запущен и доступен."
                )

        # Смотрим, какой проект сейчас активен
        # Используем повторные попытки с пересозданием app при ошибках многопоточности
        max_retries = 3
        active_project = None

        for attempt in range(max_retries):
            try:
                active_project = safe_get_active_project(app)
                if active_project is not None:
                    break  # Успешно получили активный проект
                # Если получили None (ошибка многопоточности), пересоздаем app
                if attempt < max_retries - 1:
                    print(
                        f"[DEBUG] Ошибка многопоточности при получении активного проекта (попытка {attempt + 1}/{max_retries})")
                self._thread_local.app = None
                app = powerfactory.GetApplication()
                if app is None:
                    raise RuntimeError(
                        "Не удалось получить приложение PowerFactory. "
                        "Убедитесь, что PowerFactory запущен."
                    )
                    # Небольшая задержка перед повторной попыткой
                    time.sleep(0.1)
                    continue
                else:
                    # Последняя попытка не удалась - пробуем активировать проект напрямую без проверки
                    print(
                        "[DEBUG] Все попытки получения активного проекта не удались, пробуем активировать проект напрямую")
                    try:
                        app.ActivateProject(target_project)
                        # Если активация прошла успешно, сохраняем app и возвращаем его
                        self._thread_local.app = app
                        return app
                    except Exception as e:
                        # Если и активация не удалась, возвращаем app без проверки
                        # Это позволит продолжить работу, хотя может быть нестабильно
                        print(
                            f"[DEBUG] Не удалось активировать проект напрямую: {e}")
                        print(
                            "[DEBUG] Возвращаем app без проверки активного проекта (может быть нестабильно)")
                        self._thread_local.app = app
                        return app
            except RuntimeError as e:
                # Если это не ошибка многопоточности, пробрасываем дальше
                if "can't be used from other threads" not in str(e):
                    raise
                # Если это ошибка многопоточности, пробуем активировать проект напрямую
                print(
                    f"[DEBUG] RuntimeError при получении активного проекта: {e}")
                print("[DEBUG] Пробуем активировать проект напрямую без проверки")
                try:
                    app.ActivateProject(target_project)
                    self._thread_local.app = app
                    return app
                except Exception:
                    # Если и активация не удалась, возвращаем app без проверки
                    print(
                        "[DEBUG] Возвращаем app без проверки активного проекта (может быть нестабильно)")
                    self._thread_local.app = app
                    return app
            except Exception as e:
                if attempt < max_retries - 1:
                    print(
                        f"[DEBUG] Ошибка при получении активного проекта (попытка {attempt + 1}/{max_retries}): {e}")
                    self._thread_local.app = None
                    app = powerfactory.GetApplication()
                    if app is None:
                        raise RuntimeError(
                            "Не удалось получить приложение PowerFactory. "
                            "Убедитесь, что PowerFactory запущен."
                        )
                    time.sleep(0.1)
                    continue
                else:
                    raise RuntimeError(
                        f"Ошибка при получении активного проекта PowerFactory: {e}. "
                        "Убедитесь, что PowerFactory запущен и доступен."
                    )

        active_name = None
        if active_project:
            try:
                active_name = active_project.GetAttribute("loc_name")
            except RuntimeError as e:
                if "can't be used from other threads" in str(e):
                    # Ошибка многопоточности - пересоздаем app
                    self._thread_local.app = None
                    app = powerfactory.GetApplication()
                    if app is None:
                        raise RuntimeError(
                            "Не удалось получить приложение PowerFactory. "
                            "Убедитесь, что PowerFactory запущен."
                        )
                    # Пробуем снова
                    active_project = safe_get_active_project(app)
                    if active_project:
                        try:
                            active_name = active_project.GetAttribute(
                                "loc_name")
                        except Exception:
                            active_name = None
                else:
                    raise
            except Exception:
                active_name = None

        # 1. Если уже активен нужный проект — сохраняем в thread-local и возвращаем app
        if active_name == target_project:
            self._thread_local.app = app
        return app

        # 2. Если активен другой проект — пробуем активировать нужный
        if active_name and active_name != target_project:
            try:
                app.ActivateProject(target_project)
                active_after = safe_get_active_project(app)
                if active_after:
                    try:
                        after_name = active_after.GetAttribute("loc_name")
                        if after_name == target_project:
                            self._thread_local.app = app
                            return app
                    except RuntimeError as e:
                        if "can't be used from other threads" in str(e):
                            # Ошибка многопоточности - пересоздаем app и пробуем снова
                            self._thread_local.app = None
                            app = powerfactory.GetApplication()
                            if app:
                                try:
                                    app.ActivateProject(target_project)
                                    active_after = safe_get_active_project(app)
                                    if active_after:
                                        after_name = active_after.GetAttribute(
                                            "loc_name")
                                        if after_name == target_project:
                                            self._thread_local.app = app
                                            return app
                                except Exception:
                                    pass
                        else:
                            raise
                    except Exception:
                        pass
            except RuntimeError as e:
                if "can't be used from other threads" in str(e):
                    # Ошибка многопоточности - пересоздаем app
                    self._thread_local.app = None
                    app = powerfactory.GetApplication()
                    if app:
                        try:
                            app.ActivateProject(target_project)
                            active_after = safe_get_active_project(app)
                            if active_after:
                                after_name = active_after.GetAttribute(
                                    "loc_name")
                                if after_name == target_project:
                                    self._thread_local.app = app
                                    return app
                        except Exception:
                            pass
                # Если не удалось переключить, сообщаем пользователю
                available = get_available_projects()
                msg = (
                    f"В PowerFactory открыт проект '{active_name}'.\n"
                    f"Не удалось автоматически переключить на проект '{target_project}'."
                )
                if available:
                    msg += "\nДоступные проекты: " + ", ".join(available)
                raise RuntimeError(msg)
            except Exception:
                # Если не удалось переключить, сообщаем пользователю
                available = get_available_projects()
                msg = (
                    f"В PowerFactory открыт проект '{active_name}'.\n"
                    f"Не удалось автоматически переключить на проект '{target_project}'."
                )
                if available:
                    msg += "\nДоступные проекты: " + ", ".join(available)
                raise RuntimeError(msg)

        # 3. Если нет активного проекта — пробуем активировать нужный
        try:
            app.ActivateProject(target_project)
            active_after = safe_get_active_project(app)
            if active_after:
                try:
                    after_name = active_after.GetAttribute("loc_name")
                    if after_name == target_project:
                        self._thread_local.app = app
                        return app
                except RuntimeError as e:
                    if "can't be used from other threads" in str(e):
                        # Ошибка многопоточности - пересоздаем app
                        self._thread_local.app = None
                        app = powerfactory.GetApplication()
                        if app:
                            try:
                                app.ActivateProject(target_project)
                                active_after = safe_get_active_project(app)
                                if active_after:
                                    after_name = active_after.GetAttribute(
                                        "loc_name")
                                    if after_name == target_project:
                                        self._thread_local.app = app
                                        return app
                            except Exception:
                                pass
                    else:
                        raise
                except Exception:
                    pass
        except RuntimeError as e:
            if "can't be used from other threads" in str(e):
                # Ошибка многопоточности - пересоздаем app
                self._thread_local.app = None
                app = powerfactory.GetApplication()
                if app:
                    try:
                        app.ActivateProject(target_project)
                        active_after = safe_get_active_project(app)
                        if active_after:
                            after_name = active_after.GetAttribute("loc_name")
                            if after_name == target_project:
                                self._thread_local.app = app
                                return app
                    except Exception:
                        pass
            raise RuntimeError(
                f"Ошибка при активации проекта PowerFactory: {e}. "
                f"Убедитесь, что проект '{target_project}' существует и доступен."
            )

        # 4. Не удалось активировать даже при отсутствии активного проекта
        available = get_available_projects()
        msg = f'Не удалось активировать проект "{target_project}".'
        if available:
            msg += " Доступные проекты: " + ", ".join(available)
        else:
            msg += " Не удалось получить список доступных проектов."
        raise RuntimeError(msg)

    def get_available_projects(self):
        """
        Получает список доступных проектов PowerFactory.
        Использует активный проект и пытается получить список через DataFolder.
        Использует кэширование для уменьшения частоты запросов к PowerFactory.
        При ошибках многопоточности выполняет повторные попытки с пересозданием app.

        Returns:
            List[str]: Список имен доступных проектов
        """
        # Проверяем кэш
        current_time = time.time()
        if (self._projects_cache is not None and
            (current_time - self._projects_cache_time) < self._cache_ttl):
            print(
                f"[DEBUG] Используем кэшированный список проектов (возраст: {int(current_time - self._projects_cache_time)} сек)")
            return self._projects_cache.copy()  # Возвращаем копию, чтобы не изменять кэш

        # Сохраняем старый кэш на случай ошибки многопоточности
        old_cache = self._projects_cache.copy() if self._projects_cache is not None else None
        old_cache_time = self._projects_cache_time if self._projects_cache is not None else 0

        # Инициализируем COM для текущего потока в STA режиме (если еще не инициализирован)
        # PowerFactory требует STA (Single Threaded Apartment) модель
        if pythoncom is not None:
            try:
                # Используем CoInitializeEx с COINIT_APARTMENTTHREADED для STA модели
                # COINIT_APARTMENTTHREADED = 0x2
                apartment_threaded = getattr(
                    pythoncom, 'COINIT_APARTMENTTHREADED', 0x2)
                pythoncom.CoInitializeEx(apartment_threaded)
            except Exception:
                # COM уже инициализирован в этом потоке - это нормально
                pass

        # Вспомогательная функция для безопасного получения проектов
        def safe_get_projects(app_instance, max_retries=3):
            """Безопасно получает проекты с повторными попытками при ошибках многопоточности."""
            projects_set = set()

            for attempt in range(max_retries):
                try:
                    # Очищаем thread-local app перед каждой попыткой
                    if hasattr(self._thread_local, 'app'):
                        self._thread_local.app = None

                    # Метод 1: Получаем проекты текущего пользователя (быстрее)
                    try:
                        current_user = app_instance.GetCurrentUser()
                        if current_user:
                            projects = current_user.GetContents("*.IntPrj")
                            if projects:
                                print(f"[DEBUG] Найдено проектов у текущего пользователя: {len(projects)}")
                                for proj in projects:
                                    try:
                                        name = proj.GetAttribute('loc_name')
                                        if name:
                                            projects_set.add(name)
                                            print(f"[DEBUG] Добавлен проект: {name}")
                                    except Exception as e:
                                        print(f"[DEBUG] Ошибка получения имени проекта: {e}")
                                        pass
                    except RuntimeError as e:
                        if "can't be used from other threads" in str(e):
                            print(f"[DEBUG] Ошибка многопоточности при получении проектов текущего пользователя (попытка {attempt + 1}/{max_retries})")
                            if attempt < max_retries - 1:
                                # Пересоздаем app и пробуем снова
                                import powerfactory  # type: ignore
                                app_instance = powerfactory.GetApplication()
                                if app_instance is None:
                                    break
                                time.sleep(0.1)  # Небольшая задержка перед повторной попыткой
                                continue
                            else:
                                # Последняя попытка не удалась - возвращаем пустой set, чтобы использовать кэш
                                print(f"[DEBUG] Все попытки получения проектов не удались из-за ошибки многопоточности")
                                return set()
                        else:
                            raise

                    # Если получили проекты, пробуем получить проекты всех пользователей для полноты
                    if not projects_set:
                        print("[DEBUG] Проекты не найдены у текущего пользователя, проверяем всех пользователей")
                        try:
                            users = app_instance.GetAllUsers()
                            if users:
                                print(f"[DEBUG] Найдено пользователей: {len(users)}")
                                for user in users:
                                    try:
                                        user_projects = user.GetContents("*.IntPrj")
                                        if user_projects:
                                            print(f"[DEBUG] У пользователя {user} найдено проектов: {len(user_projects)}")
                                            for proj in user_projects:
                                                try:
                                                    name = proj.GetAttribute('loc_name')
                                                    if name:
                                                        projects_set.add(name)
                                                        print(f"[DEBUG] Добавлен проект: {name}")
                                                except Exception as e:
                                                    print(f"[DEBUG] Ошибка получения имени проекта: {e}")
                                                    pass
                                    except RuntimeError as e:
                                        if "can't be used from other threads" in str(e):
                                            print(f"[DEBUG] Ошибка многопоточности при получении проектов пользователя (попытка {attempt + 1}/{max_retries})")
                                            if attempt < max_retries - 1:
                                                # Пересоздаем app и пробуем снова
                                                import powerfactory  # type: ignore
                                                app_instance = powerfactory.GetApplication()
                                                if app_instance is None:
                                                    break
                                                time.sleep(0.1)
                                                continue
                                            else:
                                                # Последняя попытка не удалась - возвращаем пустой set, чтобы использовать кэш
                                                print(f"[DEBUG] Все попытки получения проектов не удались из-за ошибки многопоточности")
                                                return set()
                                        else:
                                            raise
                                    except Exception as e:
                                        print(f"[DEBUG] Ошибка при получении проектов пользователя: {e}")
                                        pass
                        except RuntimeError as e:
                            if "can't be used from other threads" in str(e):
                                print(f"[DEBUG] Ошибка многопоточности при получении проектов всех пользователей (попытка {attempt + 1}/{max_retries})")
                                if attempt < max_retries - 1:
                                    # Пересоздаем app и пробуем снова
                                    import powerfactory  # type: ignore
                                    app_instance = powerfactory.GetApplication()
                                    if app_instance is None:
                                        break
                                    time.sleep(0.1)
                                    continue
                                else:
                                    # Последняя попытка не удалась - возвращаем пустой set, чтобы использовать кэш
                                    print(f"[DEBUG] Все попытки получения проектов не удались из-за ошибки многопоточности")
                                    return set()
                            else:
                                raise

                    # Если получили проекты, возвращаем их
                    if projects_set:
                        return projects_set

                except RuntimeError as e:
                    if "can't be used from other threads" in str(e):
                        if attempt < max_retries - 1:
                            print(f"[DEBUG] Ошибка многопоточности (попытка {attempt + 1}/{max_retries}), пересоздаем app")
                            import powerfactory  # type: ignore
                            app_instance = powerfactory.GetApplication()
                            if app_instance is None:
                                break
                            time.sleep(0.1)
                            continue
                        else:
                            # Последняя попытка не удалась - возвращаем пустой set, чтобы использовать кэш
                            print(f"[DEBUG] Все попытки получения проектов не удались из-за ошибки многопоточности")
                            return set()
                    else:
                        raise
                except Exception as e:
                    print(f"[DEBUG] Исключение при получении проектов: {e}")
                    import traceback
                    print(f"[DEBUG] Traceback: {traceback.format_exc()}")
                    if attempt < max_retries - 1:
                        import powerfactory  # type: ignore
                        app_instance = powerfactory.GetApplication()
                        if app_instance is None:
                            break
                        time.sleep(0.1)
                        continue
                    break
            
            return projects_set
        
        # Для получения списка проектов всегда создаем новый app
        # Кэшированный app может быть невалиден для текущего потока
        app = None
        
        try:
            print(f"[DEBUG] Создаем новый app для получения списка проектов")
            import powerfactory  # type: ignore
            app = powerfactory.GetApplication()
            
            if app is None:
                print(f"[DEBUG] Не удалось получить app из PowerFactory")
                # Если есть кэш, используем его
                if self._projects_cache is not None:
                    cache_age = int(time.time() - self._projects_cache_time)
                    if cache_age < self._cache_ttl * 2:
                        print(f"[DEBUG] Используем кэш, так как не удалось получить app (возраст: {cache_age} сек)")
                        return self._projects_cache.copy()
                return []
            
            # Получаем проекты с повторными попытками
            projects_set = safe_get_projects(app)
            
            # Если получили пустой set (из-за ошибки многопоточности), используем кэш
            if not projects_set:
                print("[DEBUG] Не удалось получить проекты из-за ошибки многопоточности, используем кэш")
                # Сначала проверяем текущий кэш
                if self._projects_cache is not None:
                    cache_age = int(time.time() - self._projects_cache_time)
                    # Используем кэш даже если он очень старый (до 10 минут)
                    if cache_age < 600:  # 10 минут
                        print(f"[DEBUG] Используем кэш из-за ошибки многопоточности (возраст: {cache_age} сек)")
                        return self._projects_cache.copy()
                    else:
                        print(f"[DEBUG] Кэш слишком старый ({cache_age} сек), но используем его из-за ошибки многопоточности")
                        return self._projects_cache.copy()
                # Если текущий кэш отсутствует, проверяем старый кэш (который был до попытки обновления)
                elif old_cache is not None:
                    cache_age = int(time.time() - old_cache_time)
                    # Используем старый кэш даже если он очень старый (до 10 минут)
                    if cache_age < 600:  # 10 минут
                        print(f"[DEBUG] Используем старый кэш из-за ошибки многопоточности (возраст: {cache_age} сек)")
                        # Восстанавливаем кэш
                        self._projects_cache = old_cache.copy()
                        self._projects_cache_time = old_cache_time
                        return old_cache.copy()
                    else:
                        print(f"[DEBUG] Старый кэш слишком старый ({cache_age} сек), но используем его из-за ошибки многопоточности")
                        # Восстанавливаем кэш
                        self._projects_cache = old_cache.copy()
                        self._projects_cache_time = old_cache_time
                        return old_cache.copy()
                else:
                    print("[DEBUG] Кэш отсутствует, возвращаем пустой список")
                    return []
            
            # Преобразуем set в отсортированный список
            available_projects = sorted(list(projects_set))
            
            if available_projects:
                print(f"Найдено проектов: {len(available_projects)} - {', '.join(available_projects)}")
                # Сохраняем в кэш
                self._projects_cache = available_projects.copy()
                self._projects_cache_time = time.time()
            else:
                print("Проекты не найдены")
                # Если проекты не найдены, но кэш есть - используем его
                if self._projects_cache is not None:
                    cache_age = int(time.time() - self._projects_cache_time)
                    if cache_age < self._cache_ttl * 2:  # Используем кэш даже если он немного старше
                        print(f"[DEBUG] Проекты не найдены, но используем кэш (возраст: {cache_age} сек)")
                        return self._projects_cache.copy()
            
            return available_projects
            
        except ModuleNotFoundError as e:
            print(f"ModuleNotFoundError: PowerFactory модуль не найден. Убедитесь, что PowerFactory установлен и запущен. {e}")
            # Если есть кэш, используем его
            if self._projects_cache is not None:
                cache_age = int(time.time() - self._projects_cache_time)
                if cache_age < self._cache_ttl * 2:
                    print(f"[DEBUG] Используем кэш из-за ModuleNotFoundError (возраст: {cache_age} сек)")
                    return self._projects_cache.copy()
            return []
        except RuntimeError as e:
            if "can't be used from other threads" in str(e):
                print(f"[DEBUG] Критическая ошибка многопоточности при получении списка проектов")
                # Сначала проверяем текущий кэш
                if self._projects_cache is not None:
                    cache_age = int(time.time() - self._projects_cache_time)
                    # Используем кэш даже если он очень старый (до 10 минут)
                    if cache_age < 600:  # 10 минут
                        print(f"[DEBUG] Используем кэш из-за ошибки многопоточности (возраст: {cache_age} сек)")
                        return self._projects_cache.copy()
                    else:
                        print(f"[DEBUG] Кэш слишком старый ({cache_age} сек), но используем его из-за ошибки многопоточности")
                        return self._projects_cache.copy()
                # Если текущий кэш отсутствует, проверяем старый кэш (который был до попытки обновления)
                elif old_cache is not None:
                    cache_age = int(time.time() - old_cache_time)
                    # Используем старый кэш даже если он очень старый (до 10 минут)
                    if cache_age < 600:  # 10 минут
                        print(f"[DEBUG] Используем старый кэш из-за ошибки многопоточности (возраст: {cache_age} сек)")
                        # Восстанавливаем кэш
                        self._projects_cache = old_cache.copy()
                        self._projects_cache_time = old_cache_time
                        return old_cache.copy()
                    else:
                        print(f"[DEBUG] Старый кэш слишком старый ({cache_age} сек), но используем его из-за ошибки многопоточности")
                        # Восстанавливаем кэш
                        self._projects_cache = old_cache.copy()
                        self._projects_cache_time = old_cache_time
                        return old_cache.copy()
            # Логируем ошибку для отладки
            import traceback
            error_trace = traceback.format_exc()
            print(f"Ошибка при получении списка проектов PowerFactory: {e}")
            print(f"Traceback: {error_trace}")
            # Если есть кэш, используем его
            if self._projects_cache is not None:
                cache_age = int(time.time() - self._projects_cache_time)
                if cache_age < self._cache_ttl * 2:
                    print(f"[DEBUG] Используем кэш после ошибки (возраст: {cache_age} сек)")
                    return self._projects_cache.copy()
            return []
        except Exception as e:
            # Логируем ошибку для отладки
            import traceback
            error_trace = traceback.format_exc()
            print(f"Ошибка при получении списка проектов PowerFactory: {e}")
            print(f"Traceback: {error_trace}")
            # Если есть кэш, используем его
            if self._projects_cache is not None:
                cache_age = int(time.time() - self._projects_cache_time)
                if cache_age < self._cache_ttl * 2:
                    print(f"[DEBUG] Используем кэш после исключения (возраст: {cache_age} сек)")
                    return self._projects_cache.copy()
            return []
    
    def check_project_available(self, project_name):
        """
        Проверяет, доступен ли проект PowerFactory.
        
        Args:
            project_name: Имя проекта для проверки
            
        Returns:
            bool: True если проект доступен, False если нет
        """
        available_projects = self.get_available_projects()
        return project_name in available_projects