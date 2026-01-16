import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'phase_comparison_protection.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = 'Gleb'
password = 'GP08070060'

try:
    user = User.objects.get(username=username)
    print(f"✓ Пользователь найден: '{user.username}'")
    print(f"Active: {user.is_active}")
    print(f"Has usable password: {user.has_usable_password()}")
    
    # Проверяем текущий пароль
    if user.check_password(password):
        print(f"✓ Текущий пароль правильный")
    else:
        print(f"✗ Текущий пароль неправильный")
    
    # Переустанавливаем пароль
    print(f"\nПереустанавливаем пароль...")
    user.set_password(password)
    user.is_active = True
    user.save()
    
    print(f"✓ Пароль переустановлен!")
    
    # Проверяем после переустановки
    user.refresh_from_db()
    if user.check_password(password):
        print(f"✓ Проверка пароля после переустановки: OK")
    else:
        print(f"✗ Проверка пароля после переустановки: FAILED")
        
except User.DoesNotExist:
    print(f"✗ Пользователь '{username}' не найден!")













