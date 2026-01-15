from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.conf import settings

from .forms import ADManualPasswordAuthenticationForm, normalize_ad_login


def home(request):
    return render(request, "main/home.html")


def page_not_found(request, exception):
    return render(request, "main/404.html", status=404)


class AutoLoginView(LoginView):
    """
    Кастомный LoginView для авторизации с ручным вводом пароля:
    - Шаг 1: Автозаполнение логина из Windows AD
    - Шаг 2: Проверка существования пользователя в Django
    - Шаг 3: Показ формы с readonly логином (если пользователь найден)
    - Шаг 4: Валидация пароля
    """

    form_class = ADManualPasswordAuthenticationForm
    template_name = "main/login.html"

    def dispatch(self, request, *args, **kwargs):
        # Если пользователь уже авторизован, перенаправляем на главную
        if request.user.is_authenticated:
            redirect_url = getattr(settings, "LOGIN_REDIRECT_URL", "/calculation/")
            return redirect(redirect_url)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        """Шаг 1: Предзаполняем форму данными об автоматически определенном пользователе"""
        initial = super().get_initial()

        # Получаем информацию об автоматически определенном пользователе из сессии
        auto_detected_login = self.request.session.get("auto_detected_login")
        if auto_detected_login:
            initial["username"] = auto_detected_login

        return initial

    def post(self, request, *args, **kwargs):
        """
        Обработка POST запроса согласно логике шагов:
        - Шаг 2: Проверка существования пользователя в Django
        - Шаг 3: Показ формы с readonly логином (если пользователь найден, но пароль не введен)
        - Шаг 4: Валидация пароля (если пароль введен)
        """
        form = self.get_form()
        
        if not form.is_valid():
            # Форма невалидна - есть ошибки валидации
            raw_username = request.POST.get("username", "").strip()
            
            # Проверяем тип ошибки
            has_user_not_registered = False
            has_invalid_login = False
            
            if form.errors:
                for error_list in form.errors.values():
                    for error in error_list:
                        if hasattr(error, "code"):
                            if error.code == "user_not_registered":
                                has_user_not_registered = True
                            elif error.code == "invalid_login":
                                has_invalid_login = True
            
            # Если ошибка "пользователь не зарегистрирован" - очищаем сессию
            if has_user_not_registered:
                if "user_found_for_login" in request.session:
                    del request.session["user_found_for_login"]
            # Если ошибка "неверный пароль" - сохраняем логин для readonly
            elif has_invalid_login and raw_username:
                request.session["user_found_for_login"] = raw_username
            
            return self.form_invalid(form)
        
        # Форма валидна
        # Проверяем, есть ли user_cache (успешная аутентификация)
        if hasattr(form, 'user_cache') and form.user_cache:
            # Шаг 4, Сценарий А: ВАЛИДАЦИЯ УСПЕШНА
            # Пароль правильный, пользователь авторизуется
            if "user_found_for_login" in request.session:
                del request.session["user_found_for_login"]
            return self.form_valid(form)
        else:
            # Шаг 2 → Шаг 3: Пользователь найден, но пароль не введен
            # Сохраняем в сессии для показа readonly поля
            raw_username = request.POST.get("username", "").strip()
            if raw_username:
                request.session["user_found_for_login"] = raw_username
            # Добавляем информационное сообщение
            messages.info(
                request,
                "Пользователь найден. Пожалуйста, введите пароль для входа в систему."
            )
            # Показываем форму снова с readonly логином
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get("form")

        # Получаем информацию об автоматически определенном пользователе из сессии
        auto_detected_login = self.request.session.get("auto_detected_login")

        # Определяем значение для отображения в поле username (всегда с доменом)
        display_username = None
        if form:
            # POST запрос: приоритет оригинальному значению из формы (с доменом)
            if hasattr(form, "original_username") and form.original_username:
                display_username = form.original_username
            # Если original_username еще не установлен (форма не прошла базовую валидацию),
            # используем значение из form.data (тоже с доменом)
            elif hasattr(form, "data") and form.data.get("username"):
                display_username = form.data.get("username")

        # GET запрос или если не нашли в форме: используем автоматически определенный логин
        if not display_username and auto_detected_login:
            display_username = auto_detected_login

        if display_username:
            context["auto_detected_user"] = display_username

        # Определяем, какой логин проверять: введенный пользователем или автоматически определенный
        login_to_check = None
        if form and hasattr(form, "data") and form.data.get("username"):
            # POST запрос: проверяем введенный логин
            login_to_check = form.data.get("username")
        elif auto_detected_login:
            # GET запрос: проверяем автоматически определенный логин
            login_to_check = auto_detected_login

        # Шаг 3: Блокировка поля "Логин" (readonly) только если пользователь существует в Django
        User = get_user_model()
        lock_username = False
        user_exists = False

        # Проверяем, есть ли в сессии информация о найденном пользователе
        user_found_in_session = self.request.session.get("user_found_for_login")
        
        # Проверяем, нет ли ошибки "пользователь не зарегистрирован"
        has_user_not_registered_error = False
        if form and form.errors:
            for error_list in form.errors.values():
                for error in error_list:
                    if hasattr(error, "code") and error.code == "user_not_registered":
                        has_user_not_registered_error = True
                        break
                if has_user_not_registered_error:
                    break
        
        if login_to_check and not has_user_not_registered_error:
            canonical = normalize_ad_login(login_to_check)
            user_exists = bool(
                canonical and User.objects.filter(username=canonical).exists()
            )
            
            # Блокируем поле логина если:
            # 1. Пользователь найден в БД (проверка через сессию или прямое обращение)
            # 2. И нет ошибки "пользователь не зарегистрирован"
            if user_exists or user_found_in_session:
                lock_username = True

        context["lock_username"] = lock_username
        context["user_exists"] = user_exists

        return context

    def form_valid(self, form):
        """Обработка успешной валидации формы"""
        # Очищаем флаг из сессии после успешной аутентификации
        if "user_found_for_login" in self.request.session:
            del self.request.session["user_found_for_login"]
        return super().form_valid(form)
