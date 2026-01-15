import os
import getpass
from django.utils.deprecation import MiddlewareMixin


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
            print(f"[DEBUG] Ошибка при получении имени пользователя Windows: {e}")

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

        # Уже есть значение в сессии — ничего не делаем
        if request.session.get(self.SESSION_KEY):
            return None

        domain, username = self.get_windows_identity()
        if not username:
            return None

        detected_login = f"{domain}\\{username}" if domain else username

        # Сохраняем только для страницы входа (и корня), чтобы не раздувать сессию без нужды
        if request.path == "/" or request.path == "/login/":
            request.session[self.SESSION_KEY] = detected_login

        return None
