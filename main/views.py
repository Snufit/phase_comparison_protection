from django.shortcuts import render


def home(request):
    return render(request, "main/home.html")


def page_not_found(request, exception):
    return render(request, 'main/404.html', status=404)
