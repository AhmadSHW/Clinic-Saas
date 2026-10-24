# notifications/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from accounts.decorators import login_required_session
from .models import Notification


@login_required_session
def notification_list(request):
    notifications = Notification.objects.filter(
        recipient=request.staff_user
    ).order_by("-created_at")

    return render(request, "notifications/list.html", {"notifications": notifications})


@require_POST
@login_required_session
def mark_as_read(request, notification_id):
    notification = get_object_or_404(
        Notification, id=notification_id, recipient=request.staff_user
    )
    notification.is_read = True
    notification.save()
    return redirect("notifications:list")