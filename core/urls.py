from django.urls import path

from . import views


urlpatterns = [
    path('', views.models_list_view, name='models_list'),
    path('lines/', views.lines_list_view, name='lines_list'),
    path('methodology/<int:document_id>/', views.methodology_document_view, name='methodology_document'),
]