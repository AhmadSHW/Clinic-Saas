# tenants/middleware.py
from django.utils.deprecation import MiddlewareMixin
from .models import Clinic


class CurrentClinicMiddleware(MiddlewareMixin):
    """
    Determines which clinic (tenant) the current user session belongs to,
    and attaches it to the request so every view can filter by it.
    """

    def process_request(self, request):
        clinic_id = request.session.get("clinic_id")
        request.clinic = None

        if clinic_id:
            try:
                request.clinic = Clinic.objects.get(id=clinic_id, is_active=True)
            except Clinic.DoesNotExist:
                request.session.pop("clinic_id", None)