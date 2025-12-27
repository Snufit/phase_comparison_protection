import sys
import threading
import time

try:
    import pythoncom
except ImportError:
    pythoncom = None


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
    _cache_ttl = 10  # Время жизни кэша в секундах

    def __init__(self):
        # Добавляем путь только если его еще нет в sys.path
        if self.POWERFACTORY_PATH not in sys.path:
            sys.path.append(self.POWERFACTORY_PATH)

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
                apartment_threaded = getattr(pythoncom, 'COINIT_APARTMENTTHREADED', 0x2)
                pythoncom.CoInitializeEx(apartment_threaded)
            except Exception:
                # COM уже инициализирован в этом потоке - это нормально
                # Продолжаем работу, так как COM может быть уже инициализирован
                pass
        
        # Проверяем, есть ли уже инициализированный app для этого потока
        if hasattr(self._thread_local, 'app') and self._thread_local.app is not None:
            try:
                # Проверяем, что app еще валиден и активен нужный проект
                active_project = self._thread_local.app.GetActiveProject()
                if active_project:
                    active_name = active_project.GetAttribute("loc_name")
                    if active_name == target_project:
                        return self._thread_local.app
            except RuntimeError as e:
                # Если ошибка многопоточности, очищаем app и создадим новый
                if "can't be used from other threads" in str(e):
                    self._thread_local.app = None
                else:
                    # Другие ошибки - тоже очищаем
                    self._thread_local.app = None
            except Exception:
                # Если app невалиден, очищаем и создаем новый
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

        # Смотрим, какой проект сейчас активен
        try:
            active_project = app.GetActiveProject()
        except RuntimeError as e:
            # Если ошибка многопоточности, очищаем thread-local и пробуем заново
            if "can't be used from other threads" in str(e):
                self._thread_local.app = None
                # Пытаемся получить новый app
                import powerfactory  # type: ignore
                app = powerfactory.GetApplication()
                if app is None:
                    raise RuntimeError(
                        "Не удалось получить приложение PowerFactory. "
                        "Убедитесь, что PowerFactory запущен."
                    )
                # Пробуем снова получить активный проект
                try:
                    active_project = app.GetActiveProject()
                except Exception as e2:
                    raise RuntimeError(
                        f"Ошибка при получении активного проекта PowerFactory: {e2}. "
                        "Убедитесь, что PowerFactory запущен и доступен."
                    )
            else:
                raise RuntimeError(
                    f"Ошибка при получении активного проекта PowerFactory: {e}. "
                    "Убедитесь, что PowerFactory запущен и доступен."
                )
        except Exception as e:
            raise RuntimeError(
                f"Ошибка при получении активного проекта PowerFactory: {e}. "
                "Убедитесь, что PowerFactory запущен и доступен."
            )

        active_name = None
        if active_project:
            try:
                active_name = active_project.GetAttribute("loc_name")
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
                active_after = app.GetActiveProject()
                if active_after:
                    try:
                        after_name = active_after.GetAttribute("loc_name")
                        if after_name == target_project:
                            self._thread_local.app = app
                            return app
                    except Exception:
                        pass
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
            active_after = app.GetActiveProject()
            if active_after:
                try:
                    after_name = active_after.GetAttribute("loc_name")
                    if after_name == target_project:
                        self._thread_local.app = app
                        return app
                except Exception:
                    pass
        except Exception as e:
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

        Returns: 
            List[str]: Список имен доступных проектов
        """
        # Проверяем кэш
        current_time = time.time()
        if (self._projects_cache is not None and 
            (current_time - self._projects_cache_time) < self._cache_ttl):
            print(f"[DEBUG] Используем кэшированный список проектов (возраст: {int(current_time - self._projects_cache_time)} сек)")
            return self._projects_cache.copy()  # Возвращаем копию, чтобы не изменять кэш
        
        # Инициализируем COM для текущего потока в STA режиме (если еще не инициализирован)
        # PowerFactory требует STA (Single Threaded Apartment) модель
        if pythoncom is not None:
            try:
                # Используем CoInitializeEx с COINIT_APARTMENTTHREADED для STA модели
                # COINIT_APARTMENTTHREADED = 0x2
                apartment_threaded = getattr(pythoncom, 'COINIT_APARTMENTTHREADED', 0x2)
                pythoncom.CoInitializeEx(apartment_threaded)
            except Exception:
                # COM уже инициализирован в этом потоке - это нормально
                pass
        
        # Для получения списка проектов всегда создаем новый app
        # Кэшированный app может быть невалиден для текущего потока
        # Это легкая операция, поэтому не кэшируем app для этого метода
        app = None
        
        try:
            print(f"[DEBUG] Создаем новый app для получения списка проектов")
            import powerfactory  # type: ignore
            app = powerfactory.GetApplication()
            
            if app is None:
                print(f"[DEBUG] Не удалось получить app из PowerFactory")
                return []
            
            available_projects = []
            projects_set = set()  # Используем set для избежания дубликатов
            
            # Метод 1: Получаем проекты текущего пользователя (быстрее)
            try:
                current_user = app.GetCurrentUser()
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
                    else:
                        print("[DEBUG] У текущего пользователя нет проектов")
                else:
                    print("[DEBUG] Не удалось получить текущего пользователя")
            except RuntimeError as e:
                # Если ошибка многопоточности, используем кэш если есть
                if "can't be used from other threads" in str(e):
                    print(f"[DEBUG] Ошибка многопоточности при получении проектов текущего пользователя")
                    # Очищаем кэш для этого потока
                    if hasattr(self._thread_local, 'app'):
                        self._thread_local.app = None
                    # Если есть кэш, используем его
                    if self._projects_cache is not None:
                        cache_age = int(time.time() - self._projects_cache_time)
                        if cache_age < self._cache_ttl * 2:  # Используем кэш даже если он немного старше
                            print(f"[DEBUG] Используем кэш из-за ошибки многопоточности (возраст: {cache_age} сек)")
                            return self._projects_cache.copy()
                else:
                    print(f"[DEBUG] RuntimeError при получении проектов текущего пользователя: {e}")
            except Exception as e:
                print(f"[DEBUG] Исключение при получении проектов текущего пользователя: {e}")
                import traceback
                print(f"[DEBUG] Traceback: {traceback.format_exc()}")
            
            # Метод 2: Получаем проекты всех пользователей (для полноты списка)
            # Пропускаем, если уже получили проекты из текущего пользователя
            if not projects_set:
                print("[DEBUG] Проекты не найдены у текущего пользователя, проверяем всех пользователей")
                try:
                    users = app.GetAllUsers()
                    if users:
                        print(f"[DEBUG] Найдено пользователей: {len(users)}")
                        for user in users:
                            try:
                                projects = user.GetContents("*.IntPrj")
                                if projects:
                                    print(f"[DEBUG] У пользователя {user} найдено проектов: {len(projects)}")
                                    for proj in projects:
                                        try:
                                            name = proj.GetAttribute('loc_name')
                                            if name:
                                                projects_set.add(name)
                                                print(f"[DEBUG] Добавлен проект: {name}")
                                        except Exception as e:
                                            print(f"[DEBUG] Ошибка получения имени проекта: {e}")
                                            pass
                            except Exception as e:
                                print(f"[DEBUG] Ошибка при получении проектов пользователя: {e}")
                                pass
                    else:
                        print("[DEBUG] Не найдено пользователей")
                except RuntimeError as e:
                    # Если ошибка многопоточности, используем кэш если есть
                    if "can't be used from other threads" in str(e):
                        print(f"[DEBUG] Ошибка многопоточности при получении проектов всех пользователей")
                        # Очищаем кэш для этого потока
                        if hasattr(self._thread_local, 'app'):
                            self._thread_local.app = None
                        # Если есть кэш, используем его
                        if self._projects_cache is not None:
                            cache_age = int(time.time() - self._projects_cache_time)
                            if cache_age < self._cache_ttl * 2:  # Используем кэш даже если он немного старше
                                print(f"[DEBUG] Используем кэш из-за ошибки многопоточности (возраст: {cache_age} сек)")
                                return self._projects_cache.copy()
                    else:
                        print(f"[DEBUG] RuntimeError при получении проектов всех пользователей: {e}")
                except Exception as e:
                    print(f"[DEBUG] Исключение при получении проектов всех пользователей: {e}")
                    import traceback
                    print(f"[DEBUG] Traceback: {traceback.format_exc()}")
            
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
            return []
        except Exception as e:
            # Логируем ошибку для отладки
            import traceback
            error_trace = traceback.format_exc()
            print(f"Ошибка при получении списка проектов PowerFactory: {e}")
            print(f"Traceback: {error_trace}")
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