# notifications/context_processors.py

def unread_notifications_count(request):
    """
    Makes the unread notifications count available in every template,
    for showing a badge/bell icon in the navbar.
    """
    staff_user = getattr(request, "staff_user", None)
    if staff_user:
        count = staff_user.notifications.filter(is_read=False).count()
    else:
        count = 0
    return {"unread_notifications_count": count}