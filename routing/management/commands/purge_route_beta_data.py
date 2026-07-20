from django.core.management.base import BaseCommand
from django.utils import timezone

from routing.models import RouteDiagnostic, RouteIssueReport


class Command(BaseCommand):
    help = "Delete expired route diagnostics and beta issue reports."

    def handle(self, *args, **options):
        now = timezone.now()
        diagnostics_deleted, _ = RouteDiagnostic.objects.filter(
            expires_at__lte=now
        ).delete()
        reports_deleted, _ = RouteIssueReport.objects.filter(
            expires_at__lte=now
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {diagnostics_deleted} diagnostics and "
                f"{reports_deleted} reports."
            )
        )
