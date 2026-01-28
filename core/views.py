import os
import mimetypes
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, Http404, JsonResponse
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from .models import Line, MethodologyDocument, ProtectionDevice
from .forms import MethodologyForm


def _log_core(message: str):
    """
    Вспомогательная функция для логирования через FaultCalculationService с префиксом [core].
    
    Args:
        message: Сообщение для логирования (будет добавлен префикс [core])
    """
    try:
        from calculation.services.fault_calculation_service import FaultCalculationService
        FaultCalculationService._log(f"[core] {message}")
    except ImportError:
        # Если FaultCalculationService недоступен, просто выводим в консоль
        print(f"[core] {message}")


def models_list_view(request):
    return render(request, "core/models_list.html")


def lines_list_view(request):
    lines = Line.objects.all()
    return render(request, "core/lines_list.html", {"lines": lines})


def delete_line(request, line_id):
    line = Line.objects.get(id=line_id)
    line.delete()
    return redirect("lines_list")


def methodology_document_view(request, document_id):
    """
    View для отдачи файла документа методики.
    Поддерживает как полные пути к файлам, так и относительные пути в MEDIA_ROOT.
    """
    document = get_object_or_404(MethodologyDocument, id=document_id)

    # Получаем путь к файлу из name_file
    file_path = document.name_file.strip()

    if not file_path:
        raise Http404("Путь к файлу не указан")

    # Нормализуем путь (заменяем обратные слеши на прямые для кроссплатформенности)
    file_path = file_path.replace("\\", os.sep)

    # Определяем полный путь к файлу
    full_path = None

    # Если это полный путь к файлу
    if os.path.isabs(file_path):
        if os.path.exists(file_path):
            full_path = os.path.normpath(file_path)
    # Если это относительный путь, ищем в MEDIA_ROOT
    else:
        # Убираем ведущий слеш, если есть
        if file_path.startswith("/") or file_path.startswith("\\"):
            file_path = file_path.lstrip("/\\")

        media_path = os.path.join(settings.MEDIA_ROOT, file_path)
        media_path = os.path.normpath(media_path)

        if os.path.exists(media_path):
            full_path = media_path

    # Если файл не найден
    if not full_path or not os.path.exists(full_path):
        raise Http404(f"Файл документа методики не найден: {file_path}")

    # Проверяем, что файл действительно является файлом, а не директорией
    if not os.path.isfile(full_path):
        raise Http404("Указанный путь ведет к директории, а не к файлу")

    # Определяем MIME-тип по расширению файла
    mime_type, _ = mimetypes.guess_type(full_path)
    if not mime_type:
        # По умолчанию используем application/pdf
        mime_type = "application/pdf"

    try:
        file_handle = open(full_path, "rb")
        response = FileResponse(
            file_handle, content_type=mime_type, filename=os.path.basename(full_path)
        )
        # Добавляем заголовок для отображения файла в браузере (inline)
        response[
            "Content-Disposition"
        ] = f'inline; filename="{os.path.basename(full_path)}"'
        return response
    except PermissionError:
        raise Http404("Нет доступа к файлу")
    except Exception as e:
        raise Http404(f"Ошибка при открытии файла: {e}")


@login_required
@require_http_methods(["GET", "POST"])
def add_methodology(request, device_id=None):
    """View для добавления новой методики."""
    if request.method == "POST":
        form = MethodologyForm(request.POST, request.FILES)
        if not form.is_valid():
            # Логируем ошибки формы для отладки
            import json

            _log_core(f"[DEBUG] Form is not valid")
            _log_core(
                f"[DEBUG] Form errors: {json.dumps(form.errors, ensure_ascii=False, default=str)}"
            )
            _log_core(f"[DEBUG] POST data keys: {list(request.POST.keys())}")
            _log_core(f"[DEBUG] FILES data keys: {list(request.FILES.keys())}")
            if "file" in request.FILES:
                _log_core(f"[DEBUG] File name: {request.FILES['file'].name}")
                _log_core(f"[DEBUG] File size: {request.FILES['file'].size}")
            else:
                _log_core(f"[DEBUG] No file in FILES!")
        if form.is_valid():
            # Получаем device_id из POST, если он там есть
            post_device_id = request.POST.get("device_id") or device_id

            # Получаем выбранного производителя
            manufacturer_folder = form.cleaned_data.get("manufacturer", "Другие")

            # Обрабатываем загруженный файл
            uploaded_file = form.cleaned_data.get("file")

            if not uploaded_file:
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JsonResponse(
                        {
                            "success": False,
                            "errors": {
                                "file": ["Необходимо выбрать файл для загрузки"]
                            },
                        },
                        status=400,
                    )
                messages.error(request, "Ошибка: необходимо выбрать файл для загрузки.")
                return redirect("calculation")

            # Создаем директорию для методик производителя
            methodologies_dir = os.path.join(
                settings.MEDIA_ROOT, "methodologies", manufacturer_folder
            )
            os.makedirs(methodologies_dir, exist_ok=True)

            # Генерируем уникальное имя файла
            file_name = uploaded_file.name
            # Заменяем недопустимые символы в имени файла
            import re

            file_name = re.sub(r'[<>:"/\\|?*]', "_", file_name)

            # Если файл с таким именем уже существует, добавляем номер
            base_name, ext = os.path.splitext(file_name)
            counter = 1
            while os.path.exists(os.path.join(methodologies_dir, file_name)):
                file_name = f"{base_name}_{counter}{ext}"
                counter += 1

            # Сохраняем файл
            file_path = os.path.join(methodologies_dir, file_name)
            with open(file_path, "wb+") as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            # Сохраняем относительный путь от MEDIA_ROOT с папкой производителя
            file_path_value = os.path.join(
                "methodologies", manufacturer_folder, file_name
            ).replace("\\", "/")

            # Создаем запись в БД
            methodology = MethodologyDocument.objects.create(name_file=file_path_value)
            messages.success(
                request, f'Методика "{methodology.name_file}" успешно добавлена.'
            )

            # Методика добавляется, но не устанавливается автоматически как текущая
            # Пользователь должен явно выбрать её через кнопку "Сделать текущей"

            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "success": True,
                        "message": "Методика успешно добавлена",
                        "methodology_id": methodology.id,
                        "methodology_name": methodology.name_file,
                    }
                )
            return redirect("calculation")
        else:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {"success": False, "errors": form.errors}, status=400
                )
            messages.error(request, "Ошибка при добавлении методики.")
            return redirect("calculation")
    else:
        # GET запрос - редиректим на страницу расчета
        return redirect("calculation")


@login_required
@require_http_methods(["POST"])
def delete_methodology(request, methodology_id):
    """View для удаления методики."""
    methodology = get_object_or_404(MethodologyDocument, id=methodology_id)
    methodology_name = methodology.name_file

    # Проверяем, используется ли методика устройствами
    devices_using = ProtectionDevice.objects.filter(methodology=methodology)
    devices_count = devices_using.count()

    # Отвязываем методику от всех устройств (устанавливаем в NULL)
    # Это безопасно благодаря on_delete=models.SET_NULL в модели
    if devices_count > 0:
        device_names = ", ".join([d.device_model for d in devices_using])
        devices_using.update(methodology=None)
        messages.info(
            request,
            f'Методика "{methodology_name}" отвязана от устройств: {device_names}',
        )

    # Удаляем методику
    methodology.delete()
    messages.success(request, f'Методика "{methodology_name}" успешно удалена.')

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "message": "Методика успешно удалена"})
    return redirect("calculation")


@login_required
@require_http_methods(["GET"])
def list_methodologies(request, device_id=None):
    """View для получения списка методик (AJAX)."""
    methodologies = MethodologyDocument.objects.all().order_by("-created_at")

    methodologies_list = []
    for meth in methodologies:
        methodologies_list.append(
            {
                "id": meth.id,
                "name": meth.name_file,
                "created_at": meth.created_at.strftime("%d.%m.%Y %H:%M"),
                "is_current": False,
            }
        )

    # Если указан device_id, отмечаем текущую методику устройства
    if device_id:
        try:
            device = ProtectionDevice.objects.get(id=device_id)
            if device.methodology:
                for meth in methodologies_list:
                    if meth["id"] == device.methodology.id:
                        meth["is_current"] = True
                        break
        except ProtectionDevice.DoesNotExist:
            pass

    return JsonResponse({"methodologies": methodologies_list})


def _get_manufacturer_from_methodology_path(methodology):
    """
    Извлекает производителя из пути методики.
    
    :param methodology: Экземпляр MethodologyDocument
    :return: Название производителя ("ЭКРА", "Релематика", "Бреслер", "Другие") или None
    """
    if not methodology or not methodology.name_file:
        return None
    
    name_file_lower = methodology.name_file.lower()
    path_parts = name_file_lower.replace("\\", "/").split("/")
    
    # Ищем папку производителя в пути (обычно это второй элемент после 'methodologies')
    if len(path_parts) >= 2 and path_parts[0] == "methodologies":
        manufacturer_in_path = path_parts[1]
        if "экра" in manufacturer_in_path:
            return "ЭКРА"
        elif "релематика" in manufacturer_in_path:
            return "Релематика"
        elif "бреслер" in manufacturer_in_path or "нпп" in manufacturer_in_path:
            return "Бреслер"
        else:
            return "Другие"
    else:
        # Для обратной совместимости: проверяем имя файла
        if "экра" in name_file_lower:
            return "ЭКРА"
        elif "релематика" in name_file_lower:
            return "Релематика"
        elif "бреслер" in name_file_lower or "нпп" in name_file_lower:
            return "Бреслер"
        else:
            return "Другие"


def _get_manufacturer_category_from_device(device):
    """
    Определяет категорию производителя устройства защиты.
    
    :param device: Экземпляр ProtectionDevice
    :return: Название категории производителя ("ЭКРА", "Релематика", "Бреслер") или None
    """
    if not device or not device.manufacturer_fk:
        return None
    
    manufacturer_name = device.manufacturer_fk.name.upper()
    
    if "ЭКРА" in manufacturer_name:
        return "ЭКРА"
    elif "РЕЛЕМАТИКА" in manufacturer_name:
        return "Релематика"
    elif "БРЕСЛЕР" in manufacturer_name or "НПП" in manufacturer_name:
        return "Бреслер"
    
    return None


def _check_manufacturer_compatibility(methodology, device):
    """
    Проверяет совместимость производителя методики и устройства защиты.
    
    :param methodology: Экземпляр MethodologyDocument
    :param device: Экземпляр ProtectionDevice
    :return: (is_compatible: bool, error_message: str)
    """
    methodology_manufacturer = _get_manufacturer_from_methodology_path(methodology)
    device_manufacturer = _get_manufacturer_category_from_device(device)
    
    # Если у устройства нет производителя, разрешаем установку
    if not device_manufacturer:
        return True, None
    
    # Если у методики нет производителя или это "Другие", разрешаем установку
    if not methodology_manufacturer or methodology_manufacturer == "Другие":
        return True, None
    
    # Проверяем совпадение производителей
    if methodology_manufacturer != device_manufacturer:
        return False, (
            f"Нельзя установить методику производителя '{methodology_manufacturer}' "
            f"для устройства производителя '{device.manufacturer_fk.name}'. "
            f"Методика и устройство должны быть от одного производителя."
        )
    
    return True, None


@login_required
@require_http_methods(["POST"])
def set_methodology(request, methodology_id, device_id=None):
    """View для установки методики как текущей для устройства защиты."""
    methodology = get_object_or_404(MethodologyDocument, id=methodology_id)
    
    # Получаем device_id из POST, если он там есть, иначе из URL
    post_device_id = request.POST.get("device_id") or device_id
    
    if not post_device_id:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": False,
                    "message": "Не указано устройство защиты"
                },
                status=400
            )
        messages.error(request, "Ошибка: не указано устройство защиты.")
        return redirect("calculation")
    
    try:
        device = ProtectionDevice.objects.get(id=post_device_id)
        
        # Проверяем совместимость производителей
        is_compatible, error_message = _check_manufacturer_compatibility(methodology, device)
        
        if not is_compatible:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "success": False,
                        "message": error_message
                    },
                    status=400
                )
            messages.error(request, error_message)
            return redirect("calculation")
        
        device.methodology = methodology
        device.save()
        
        # Обновляем объект из базы данных для гарантии актуальности данных
        device.refresh_from_db()
        
        messages.success(
            request,
            f'Методика "{methodology.get_filename()}" установлена как текущая для устройства "{device.device_model}".'
        )
        
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": True,
                    "message": "Методика успешно установлена как текущая",
                    "methodology_id": methodology.id,
                    "methodology_name": methodology.get_filename(),
                    "device_id": device.id,
                }
            )
        return redirect("calculation")
    except (ProtectionDevice.DoesNotExist, ValueError) as e:
        _log_core(f"[ERROR] Ошибка при установке методики: {e}")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "success": False,
                    "message": "Устройство защиты не найдено"
                },
                status=404
            )
        messages.error(request, "Ошибка: устройство защиты не найдено.")
        return redirect("calculation")