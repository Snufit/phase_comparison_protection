from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm


User = get_user_model()


def normalize_ad_login(value: str) -> str:
    """
    Приводит логин вида:
    - DOMAIN\\username
    - username@domain
    - username
    к username (как хранится в Django User.username).
    """
    value = (value or "").strip()
    if "\\" in value:
        # DOMAIN\username -> username
        return value.split("\\", 1)[1].strip()
    if "@" in value:
        # username@domain -> username
        return value.split("@", 1)[0].strip()
    return value


class ADManualPasswordAuthenticationForm(AuthenticationForm):
    """
    Логика "AD автозаполнение + ручной пароль":
    - Поле username может прийти как DOMAIN\\username, но ищем/валидируем в Django по username.
    - Шаг 2: Если пользователя нет в БД Django -> отдельная понятная ошибка.
    - Шаг 4: Если пользователь есть -> стандартная проверка пароля через authenticate().
    """

    username = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Имя пользователя",
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control"}), 
        label="Пароль",
        required=False  # Пароль необязателен для Шага 2 (проверка существования пользователя)
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "user_not_registered": (
            "Пользователь не зарегистрирован в системе. "
            "Обратитесь к администратору для создания учетной записи."
        ),
        "invalid_login": (
            "Неверный пароль. Пожалуйста, проверьте правильность введенного пароля и попробуйте снова."
        ),
        "inactive": (
            "Учетная запись заблокирована. Обратитесь к администратору для разблокировки."
        ),
    }

    def clean_username(self):
        """Нормализуем username ДО вызова clean()"""
        raw_username = self.cleaned_data.get("username", "")
        if raw_username:
            # Сохраняем оригинальное значение для отображения
            self.original_username = raw_username
            # Нормализуем для проверки в БД
            normalized = normalize_ad_login(raw_username)
            return normalized
        return raw_username

    def clean(self):
        """
        Логика валидации по шагам:
        - Шаг 2: Проверка существования пользователя (всегда выполняется)
        - Шаг 4: Валидация пароля (только если пароль введен)
        """
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password", "").strip()
        
        raw_username = self.data.get("username", "").strip()
        
        if not raw_username:
            raise forms.ValidationError("Логин обязателен для заполнения.")

        # Сохраняем оригинальное значение для отображения (с доменом)
        self.original_username = raw_username
        
        # Нормализуем логин для проверки в БД
        normalized_username = normalize_ad_login(raw_username)
        
        if not normalized_username:
            raise forms.ValidationError("Некорректный формат логина.")
        
        # Убеждаемся, что username нормализован в cleaned_data
            self.cleaned_data["username"] = normalized_username
        
        # Шаг 2: Проверка существования пользователя в Django
        # (выполняется всегда, независимо от наличия пароля)
        try:
            user = User.objects.get(username=normalized_username)
            if not user.is_active:
                # Учетная запись заблокирована
                raise forms.ValidationError(
                    "Учетная запись заблокирована. Обратитесь к администратору.",
                    code="inactive",
                )
            # Пользователь найден и активен - сохраняем в форме
            self.found_user = user
        except User.DoesNotExist:
            # Шаг 2, Сценарий Б: Пользователь НЕ НАЙДЕН в Django
            # Очищаем форму и показываем ошибку
            raise forms.ValidationError(
                self.error_messages["user_not_registered"],
                code="user_not_registered",
            )
        
        # Шаг 4: Валидация пароля (только если пароль введен)
        if password:
            # Используем нормализованное имя для authenticate()
            self.user_cache = authenticate(
                self.request, username=normalized_username, password=password
            )
            
            if self.user_cache is None:
                # Шаг 4, Сценарий Б: ВАЛИДАЦИЯ НЕУДАЧНА
                # Пароль неправильный или проблемы с аутентификацией
                raise forms.ValidationError(
                    self.error_messages["invalid_login"],
                    code="invalid_login",
                )
            else:
                # Шаг 4, Сценарий А: ВАЛИДАЦИЯ УСПЕШНА
                self.confirm_login_allowed(self.user_cache)
        else:
            # Пароль не введен - это Шаг 2 → Шаг 3
            # Пользователь найден, но пароль еще не введен
            # Форма считается валидной, но user_cache не устанавливается
            # View обработает это и покажет форму с readonly логином
            self.user_cache = None

        return self.cleaned_data
