from django.shortcuts import render, redirect
from .models import Line


def models_list_view(request):
    return render(request, 'core/models_list.html')


def lines_list_view(request):
    lines = Line.objects.all()
    return render(request, 'core/lines_list.html', {'lines': lines})


def delete_line(request, line_id):
    line = Line.objects.get(id=line_id)
    line.delete()
    return redirect('lines_list')