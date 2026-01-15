# core/management/commands/debug_auth.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model, authenticate
from django.test import RequestFactory
from main.forms import normalize_ad_login

User = get_user_model()


class Command(BaseCommand):
    help = 'Диагностика аутентификации пользователя'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            default='GLEB-V6D1NN2\\Gleb',
            help='Имя пользователя для тестирования'
        )
        parser.add_argument(
            '--password',
            type=str,
            required=True,
            help='Пароль для тестирования'
        )

    def handle(self, *args, **options):
        raw_username = options['username']
        test_password = options['password']

        self.stdout.write("=" * 60)
        self.stdout.write("ДИАГНОСТИКА АУТЕНТИФИКАЦИИ")
        self.stdout.write("=" * 60)

        # 1. Проверка нормализации
        normalized = normalize_ad_login(raw_username)
        self.stdout.write(f"\n1. Нормализация username:")
        self.stdout.write(f"   Исходный: '{raw_username}'")
        self.stdout.write(f"   Нормализованный: '{normalized}'")
        self.stdout.write(f"   Длина: {len(normalized)}")

        # 2. Поиск пользователя в БД
        self.stdout.write(f"\n2. Поиск пользователя в БД:")
        try:
            user = User.objects.get(username=normalized)
            self.stdout.write(self.style.SUCCESS(f"   ✓ Пользователь найден: '{user.username}'"))
            self.stdout.write(f"   Active: {user.is_active}")
            self.stdout.write(f"   Has usable password: {user.has_usable_password()}")
            self.stdout.write(f"   Password hash: {user.password[:50]}...")
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"   ✗ Пользователь '{normalized}' НЕ найден!"))
            self.stdout.write(f"\n   Доступные пользователи:")
            for u in User.objects.all():
                self.stdout.write(f"     - '{u.username}' (active: {u.is_active})")
            return

        # 3. Проверка всех вариантов username
        self.stdout.write(f"\n3. Проверка вариантов username:")
        variants = [
            normalized,
            normalized.lower(),
            normalized.upper(),
            normalized.strip(),
            "Gleb",
            "gleb",
            "GLEB",
        ]
        for variant in variants:
            exists = User.objects.filter(username=variant).exists()
            status = self.style.SUCCESS('✓') if exists else self.style.ERROR('✗')
            self.stdout.write(f"   '{variant}': {status}")

        # 4. Тест аутентификации
        self.stdout.write(f"\n4. Тест authenticate():")
        self.stdout.write(f"   Username: '{normalized}'")
        self.stdout.write(f"   Password: '{test_password}'")

        factory = RequestFactory()
        request = factory.post('/')

        auth_user = authenticate(request, username=normalized, password=test_password)
        if auth_user:
            self.stdout.write(self.style.SUCCESS(f"   ✓ Аутентификация УСПЕШНА!"))
            self.stdout.write(f"   User: {auth_user.username}")
        else:
            self.stdout.write(self.style.ERROR(f"   ✗ Аутентификация НЕУДАЧНА!"))
            
            # Проверяем пароль вручную
            self.stdout.write(f"\n5. Проверка пароля вручную:")
            if user.check_password(test_password):
                self.stdout.write(self.style.SUCCESS(f"   ✓ Пароль ПРАВИЛЬНЫЙ (check_password вернул True)"))
                self.stdout.write(self.style.WARNING("   ⚠ Но authenticate() не работает. Возможна проблема с AUTHENTICATION_BACKENDS"))
            else:
                self.stdout.write(self.style.ERROR(f"   ✗ Пароль НЕПРАВИЛЬНЫЙ (check_password вернул False)"))
                self.stdout.write(f"\n   Попробуйте переустановить пароль:")
                self.stdout.write(f"   python manage.py shell")
                self.stdout.write(f"   >>> from django.contrib.auth import get_user_model")
                self.stdout.write(f"   >>> User = get_user_model()")
                self.stdout.write(f"   >>> user = User.objects.get(username='{normalized}')")
                self.stdout.write(f"   >>> user.set_password('{test_password}')")
                self.stdout.write(f"   >>> user.save()")

        self.stdout.write("\n" + "=" * 60)