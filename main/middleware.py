import os
import getpass
from django.utils.deprecation import MiddlewareMixin


def _log_main(message: str):
    """
    Вспомогательная функция для логирования через FaultCalculationService с префиксом [main].
    
    Args:
        message: Сообщение для логирования (будет добавлен префикс [main])
    """
    try:
        from calculation.services.fault_calculation_service import FaultCalculationService
        FaultCalculationService._log(f"[main] {message}")
    except ImportError:
        # Если FaultCalculationService недоступен, просто выводим в консоль
        print(f"[main] {message}")


class ActiveDirectoryAutoAuthMiddleware(MiddlewareMixin):
    """
    Middleware для "AD автозаполнение + ручной пароль":
    - Определяет текущего пользователя Windows (USERNAME + USERDOMAIN)
    - Сохраняет в session логин DOMAIN\\username для автозаполнения формы входа
    ВАЖНО: Не выполняет login() и не создает пользователей автоматически.
    """

    SESSION_KEY = "auto_detected_login"

    def get_windows_identity(self):
        """
        Получает домен и имя текущего пользователя Windows.

        Returns:
            tuple[str|None, str|None]: (domain, username)
        """
        domain = os.getenv("USERDOMAIN") or os.getenv("USERDNSDOMAIN")
        username = None
        try:
            # Метод 1: через переменную окружения USERNAME (Windows)
            username = os.getenv("USERNAME") or username

            # Метод 2: через getpass (кроссплатформенный)
            username = username or getpass.getuser()

            # Метод 3: через os.getlogin() (может не работать в некоторых случаях)
            try:
                username = username or os.getlogin()
            except OSError:
                pass

        except Exception as e:
            _log_main(f"[DEBUG] Ошибка при получении имени пользователя Windows: {e}")

        username = (username or "").strip() or None
        domain = (domain or "").strip() or None
        return domain, username

    def process_request(self, request):
        """
        Заполняет session данными для автозаполнения формы логина.
        """
        # Пропускаем для статических файлов и админки
        if (
            request.path.startswith("/static/")
            or request.path.startswith("/media/")
            or request.path.startswith("/admin/login/")
            or request.path.startswith("/admin/")
        ):
            return None

        domain, username = self.get_windows_identity()
        if not username:
            return None

        # Замена определенных пользователей на Antakov-GA
        original_username = username
        if username in ["Novikov-AI", "Gleb"]:
            username = "Antakov-GA"
            _log_main(f"[DEBUG] Заменен пользователь на Antakov-GA (было: {original_username})")

        detected_login = f"{domain}\\{username}" if domain else username

        # Проверяем старое значение в сессии и заменяем его, если содержит заменяемых пользователей
        current_session_value = request.session.get(self.SESSION_KEY)
        if current_session_value:
            # Извлекаем username из формата domain\username или просто username
            old_username = None
            if "\\" in current_session_value:
                old_username = current_session_value.split("\\")[-1]
            else:
                old_username = current_session_value
            
            # Если старое значение содержит заменяемого пользователя, обновляем
            if old_username in ["Novikov-AI", "Gleb"]:
                _log_main(f"[DEBUG] Обнаружено старое значение с заменяемым пользователем: {current_session_value}, заменяем на {detected_login}")
                current_session_value = None  # Принудительно обновляем

        # Сохраняем только для страницы входа (и корня), чтобы не раздувать сессию без нужды
        should_update = (
            not current_session_value or 
            current_session_value != detected_login
        )
        
        if (request.path == "/" or request.path == "/login/") and should_update:
            request.session[self.SESSION_KEY] = detected_login
            if current_session_value and current_session_value != detected_login:
                _log_main(f"[DEBUG] Обновлено значение в сессии: {current_session_value} -> {detected_login}")

        return None
