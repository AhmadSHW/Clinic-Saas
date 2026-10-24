# patients/decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from .models import Patient


def login_required_patient(view_func):
    """Ensures a patient is logged in to the portal (separate from staff sessions)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        patient_id = request.session.get("patient_id")
        if not patient_id:
            messages.error(request, "Please log in to continue.")
            return redirect("dashboard:landing")

        try:
            request.patient = Patient.objects.select_related("clinic").get(
                id=patient_id, is_active=True, clinic__is_active=True
            )
        except Patient.DoesNotExist:
            request.session.pop("patient_id", None)
            messages.error(request, "Please log in to continue.")
            return redirect("dashboard:landing")

        if request.patient.clinic.needs_subscription:
            request.session.pop("patient_id", None)
            messages.error(request, "This clinic's online portal is currently unavailable.")
            return redirect("dashboard:landing")

        return view_func(request, *args, **kwargs)

    return wrapper