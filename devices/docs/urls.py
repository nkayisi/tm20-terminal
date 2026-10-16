"""URLs de la documentation publique."""

from django.urls import path

from . import views

app_name = 'docs'

urlpatterns = [
    path(
        'pointages/',
        views.AttendancePayloadDocView.as_view(),
        name='attendance_payload',
    ),
]
