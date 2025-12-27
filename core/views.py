import os
import mimetypes
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, Http404
from django.conf import settings
from .models import Line, MethodologyDocument


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