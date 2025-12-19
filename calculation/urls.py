from django.urls import path

from . import views

urlpatterns = [
    path(
        "",
        views.CalculationView.as_view(),
        name="calculation"
    ),
    path(
        "results/<int:calculation_meta_id>",
        views.calculation_results,
        name="results"
    ),
    path(
        "sensitivity_analysis/<int:calculation_meta_id>",
        views.sensitivity_analysis,
        name="sensitivity_analysis",
    ),
    path(
        "calculation_list/",
        views.calculation_list,
        name="calculation_list"
    ),
    path(
        "sensitivity-chart/",
        views.sensitivity_chart_view,
        name="sensitivity_chart"
    ),
    path(
        "sensitivity_analysis/export/<int:calculation_meta_id>/",
        views.export_sensitivity_analysis,
        name="export_sensitivity_analysis",
    ),
    path(
        "settings_calculation/export/<int:calculation_meta_id>/",
        views.export_calculation_results,
        name="export_calculation_results",
    ),
    path(
        'test/',
        views.TestView.as_view(),
        name='test'
    ),
    path(
        'filter-lines/',
        views.filter_lines_ajax,
        name='filter_lines_ajax'
    )
]
