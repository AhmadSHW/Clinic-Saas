# appointments/urls.py
from django.urls import path
from . import views

app_name = "appointments"

urlpatterns = [
    path("", views.appointment_list, name="list"),
    path("book/", views.book_appointment, name="book"),
    path("<int:appointment_id>/check-in/", views.check_in, name="check_in"),
    path("<int:appointment_id>/complete/", views.complete_appointment, name="complete"),
    path("<int:appointment_id>/cancel/", views.cancel_appointment, name="cancel"),
    path("queue/", views.queue_view, name="queue"),
]