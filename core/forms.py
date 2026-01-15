from django import forms
from .models import MethodologyDocument


class MethodologyForm(forms.Form):
    """Форма для добавления новой методики."""

    manufacturer = forms.ChoiceField(
        label="Производитель",
        choices=[
            ("ЭКРА", "ЭКРА"),
            ("Релематика", "Релематика"),
            ("Бреслер", "Бреслер"),
            ("Другие", "Другие"),
        ],
        required=True,
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    file = forms.FileField(
        label="Выберите файл методики",
        required=True,
        help_text="Загрузите файл методики (PDF, DOC, DOCX и т.д.)",
        widget=forms.FileInput(
            attrs={"class": "form-control", "accept": ".pdf,.doc,.docx"}
        ),
    )
