# appointments/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Max
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import login_required_session
from accounts.models import StaffUser
from patients.models import Patient
from notifications.models import Notification
from .models import Appointment
from .utils import parse_scheduled_at, today_range



@login_required_session
def appointment_list(request):
    appointments = Appointment.objects.filter(clinic=request.clinic).exclude(
        status=Appointment.Status.COMPLETED
    )

    # ?doctor=<id> shows one doctor's appointments (Doctors page, "My Appointments")
    doctor = None
    doctor_id = request.GET.get("doctor", "")
    if doctor_id.isdigit():
        doctor = get_object_or_404(
            StaffUser, id=doctor_id, clinic=request.clinic, role=StaffUser.Role.DOCTOR
        )
        appointments = appointments.filter(doctor=doctor)

    return render(request, "appointments/list.html", {
        "appointments": appointments,
        "filter_doctor": doctor,
    })


@login_required_session
def book_appointment(request):
    patients = Patient.objects.filter(clinic=request.clinic)
    doctors = StaffUser.objects.filter(
        clinic=request.clinic, role=StaffUser.Role.DOCTOR, is_active=True
    )
    context = {
        "patients": patients,
        "doctors": doctors,
        # ?doctor=<id> (from the Doctors page) pre-selects the doctor
        "selected_doctor": request.POST.get("doctor_id") or request.GET.get("doctor", ""),
    }

    if request.method == "POST":
        patient_id = request.POST.get("patient_id")
        doctor_id = request.POST.get("doctor_id")
        reason = request.POST.get("reason", "").strip()

        patient = get_object_or_404(patients, id=patient_id)
        doctor = get_object_or_404(doctors, id=doctor_id)

        scheduled_at = parse_scheduled_at(request.POST.get("scheduled_at"))
        if not scheduled_at:
            messages.error(request, "Please enter a valid date and time.")
            return render(request, "appointments/book.html", context)

        appointment = Appointment.objects.create(
            clinic=request.clinic,
            patient=patient,
            doctor=doctor,
            scheduled_at=scheduled_at,
            reason=reason,
            status=Appointment.Status.CONFIRMED,
        )

        Notification.objects.create(
            clinic=request.clinic,
            recipient=doctor,
            patient=patient,
            notification_type=Notification.NotificationType.NEW_APPOINTMENT,
            title="New Appointment",
            message=f"New appointment with {patient.full_name} on {appointment.scheduled_at.strftime('%Y-%m-%d %H:%M')}",
        )

        messages.success(request, "Appointment booked successfully.")
        return redirect("appointments:list")

    return render(request, "appointments/book.html", context)


@require_POST
@login_required_session
def check_in(request, appointment_id):
    """Marks a patient as checked in and adds them to the waiting queue."""
    appointment = get_object_or_404(Appointment, id=appointment_id, clinic=request.clinic)

    if appointment.status not in (Appointment.Status.PENDING, Appointment.Status.CONFIRMED):
        messages.error(request, "Only pending or confirmed appointments can be checked in.")
        return redirect("appointments:list")

    # Queue position = highest position handed out today for this doctor, + 1
    # (a ticket number, so it never repeats when earlier patients are completed)
    day_start, day_end = today_range()
    last_position = Appointment.objects.filter(
        clinic=request.clinic,
        doctor=appointment.doctor,
        checked_in_at__gte=day_start,
        checked_in_at__lt=day_end,
    ).aggregate(Max("queue_position"))["queue_position__max"] or 0

    appointment.status = Appointment.Status.IN_QUEUE
    appointment.checked_in_at = timezone.now()
    appointment.queue_position = last_position + 1
    appointment.save()

    messages.success(request, f"{appointment.patient.full_name} checked in (queue #{appointment.queue_position}).")
    return redirect("appointments:queue")


@require_POST
@login_required_session
def complete_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, clinic=request.clinic)

    if appointment.status != Appointment.Status.IN_QUEUE:
        messages.error(request, "Only checked-in appointments can be completed.")
        return redirect("appointments:queue")

    appointment.status = Appointment.Status.COMPLETED
    appointment.save()
    messages.success(request, "Appointment marked as completed.")
    return redirect("appointments:queue")


@require_POST
@login_required_session
def cancel_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, clinic=request.clinic)

    if appointment.status in (Appointment.Status.COMPLETED, Appointment.Status.CANCELLED):
        messages.error(request, "This appointment can no longer be cancelled.")
        return redirect("appointments:list")

    appointment.status = Appointment.Status.CANCELLED
    appointment.save()

    # The doctor may have been deleted (doctor FK is SET_NULL)
    if appointment.doctor:
        Notification.objects.create(
            clinic=request.clinic,
            recipient=appointment.doctor,
            patient=appointment.patient,
            notification_type=Notification.NotificationType.APPOINTMENT_CANCELLED,
            title="Appointment Cancelled",
            message=f"Appointment with {appointment.patient.full_name} was cancelled.",
        )

    messages.info(request, "Appointment cancelled.")
    return redirect("appointments:list")


@login_required_session
def queue_view(request):
    """Real-time-style waiting queue, grouped and ordered by doctor then position."""
    queue = Appointment.objects.filter(
        clinic=request.clinic,
        status=Appointment.Status.IN_QUEUE,
    ).order_by("doctor__full_name", "queue_position")

    return render(request, "appointments/queue.html", {"queue": queue})