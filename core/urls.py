from django.urls import path

from . import views


urlpatterns = [
    path("", views.models_list_view, name="models_list"),
    path("lines/", views.lines_list_view, name="lines_list"),
    path(
        "methodology/<int:document_id>/",
        views.methodology_document_view,
        name="methodology_document",
    ),
    path("methodology/add/", views.add_methodology, name="add_methodology"),
    path(
        "methodology/add/<int:device_id>/",
        views.add_methodology,
        name="add_methodology_for_device",
    ),
    path(
        "methodology/delete/<int:methodology_id>/",
        views.delete_methodology,
        name="delete_methodology",
    ),
    path("methodology/list/", views.list_methodologies, name="list_methodologies"),
    path(
        "methodology/list/<int:device_id>/",
        views.list_methodologies,
        name="list_methodologies_for_device",
    ),
]
