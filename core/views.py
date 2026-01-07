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


def models_list_view(request):
    return render(request, 'core/models_list.html')


def lines_list_view(request):
    lines = Line.objects.all()
    return render(request, 'core/lines_list.html', {'lines': lines})


def delete_line(request, line_id):
    line = Line.objects.get(id=line_id)
    line.delete()
    return redirect('lines_list')


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
    file_path = file_path.replace('\\', os.sep)
    
    # Определяем полный путь к файлу
    full_path = None
    
    # Если это полный путь к файлу
    if os.path.isabs(file_path):
        if os.path.exists(file_path):
            full_path = os.path.normpath(file_path)
    # Если это относительный путь, ищем в MEDIA_ROOT
    else:
        # Убираем ведущий слеш, если есть
        if file_path.startswith('/') or file_path.startswith('\\'):
            file_path = file_path.lstrip('/\\')
        
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
        mime_type = 'application/pdf'
    
    try:
        file_handle = open(full_path, 'rb')
        response = FileResponse(
            file_handle,
            content_type=mime_type,
            filename=os.path.basename(full_path)
        )
        # Добавляем заголовок для отображения файла в браузере (inline)
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(full_path)}"'
        return response
    except PermissionError:
        raise Http404("Нет доступа к файлу")
    except Exception as e:
        raise Http404(f"Ошибка при открытии файла: {e}")


@login_required
@require_http_methods(["GET", "POST"])
def add_methodology(request, device_id=None):
    """View для добавления новой методики."""
    if request.method == 'POST':
        form = MethodologyForm(request.POST, request.FILES)
        if not form.is_valid():
            # Логируем ошибки формы для отладки
            import json
            print(f"[DEBUG] Form is not valid")
            print(f"[DEBUG] Form errors: {json.dumps(form.errors, ensure_ascii=False, default=str)}")
            print(f"[DEBUG] POST data keys: {list(request.POST.keys())}")
            print(f"[DEBUG] FILES data keys: {list(request.FILES.keys())}")
            if 'file' in request.FILES:
                print(f"[DEBUG] File name: {request.FILES['file'].name}")
                print(f"[DEBUG] File size: {request.FILES['file'].size}")
            else:
                print(f"[DEBUG] No file in FILES!")
        if form.is_valid():
            # Получаем device_id из POST, если он там есть
            post_device_id = request.POST.get('device_id') or device_id
            
            # Получаем выбранного производителя
            manufacturer_folder = form.cleaned_data.get('manufacturer', 'Другие')
            
            # Обрабатываем загруженный файл
            uploaded_file = form.cleaned_data.get('file')
            
            if not uploaded_file:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': {'file': ['Необходимо выбрать файл для загрузки']}
                    }, status=400)
                messages.error(request, 'Ошибка: необходимо выбрать файл для загрузки.')
                return redirect('calculation')
            
            # Создаем директорию для методик производителя
            methodologies_dir = os.path.join(settings.MEDIA_ROOT, 'methodologies', manufacturer_folder)
            os.makedirs(methodologies_dir, exist_ok=True)
            
            # Генерируем уникальное имя файла
            file_name = uploaded_file.name
            # Заменяем недопустимые символы в имени файла
            import re
            file_name = re.sub(r'[<>:"/\\|?*]', '_', file_name)
            
            # Если файл с таким именем уже существует, добавляем номер
            base_name, ext = os.path.splitext(file_name)
            counter = 1
            while os.path.exists(os.path.join(methodologies_dir, file_name)):
                file_name = f"{base_name}_{counter}{ext}"
                counter += 1
            
            # Сохраняем файл
            file_path = os.path.join(methodologies_dir, file_name)
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            # Сохраняем относительный путь от MEDIA_ROOT с папкой производителя
            file_path_value = os.path.join('methodologies', manufacturer_folder, file_name).replace('\\', '/')
            
            # Создаем запись в БД
            methodology = MethodologyDocument.objects.create(name_file=file_path_value)
            messages.success(request, f'Методика "{methodology.name_file}" успешно добавлена.')
            
            # Если указан device_id, привязываем методику к устройству
            if post_device_id:
                try:
                    device = ProtectionDevice.objects.get(id=post_device_id)
                    device.methodology = methodology
                    device.save()
                    messages.info(request, f'Методика привязана к устройству "{device.device_model}".')
                except (ProtectionDevice.DoesNotExist, ValueError):
                    pass
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Методика успешно добавлена',
                    'methodology_id': methodology.id,
                    'methodology_name': methodology.name_file
                })
            return redirect('calculation')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
            messages.error(request, 'Ошибка при добавлении методики.')
            return redirect('calculation')
    else:
        # GET запрос - редиректим на страницу расчета
        return redirect('calculation')


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
        device_names = ', '.join([d.device_model for d in devices_using])
        devices_using.update(methodology=None)
        messages.info(
            request,
            f'Методика "{methodology_name}" отвязана от устройств: {device_names}'
        )
    
    # Удаляем методику
    methodology.delete()
    messages.success(request, f'Методика "{methodology_name}" успешно удалена.')
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'Методика успешно удалена'
        })
    return redirect('calculation')


@login_required
@require_http_methods(["GET"])
def list_methodologies(request, device_id=None):
    """View для получения списка методик (AJAX)."""
    methodologies = MethodologyDocument.objects.all().order_by('-created_at')
    
    methodologies_list = []
    for meth in methodologies:
        methodologies_list.append({
            'id': meth.id,
            'name': meth.name_file,
            'created_at': meth.created_at.strftime('%d.%m.%Y %H:%M'),
            'is_current': False
        })
    
    # Если указан device_id, отмечаем текущую методику устройства
    if device_id:
        try:
            device = ProtectionDevice.objects.get(id=device_id)
            if device.methodology:
                for meth in methodologies_list:
                    if meth['id'] == device.methodology.id:
                        meth['is_current'] = True
                        break
        except ProtectionDevice.DoesNotExist:
            pass
    
    return JsonResponse({
        'methodologies': methodologies_list
    })