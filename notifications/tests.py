from tenants.testing import ClinicTestCase
from .models import Notification


class NotificationTests(ClinicTestCase):
    def make_notification(self, recipient):
        return Notification.objects.create(
            clinic=self.clinic, recipient=recipient,
            notification_type=Notification.NotificationType.GENERAL, title="Hi", message="Hello",
        )

    def test_mark_read_requires_post(self):
        notification = self.make_notification(self.admin)
        self.login_as()
        url = f"/en/notifications/{notification.id}/read/"

        self.assertEqual(self.c.get(url).status_code, 405)
        self.c.post(url)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_cannot_mark_someone_elses_notification(self):
        notification = self.make_notification(self.doc)
        self.login_as()
        self.assertEqual(self.c.post(f"/en/notifications/{notification.id}/read/").status_code, 404)
