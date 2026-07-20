from django.core.management.base import BaseCommand

from routing.diagnostics import purge_expired_beta_records
from routing.models import RouteDiagnostic, RouteIssueReport


class Command(BaseCommand):
    help = "Delete expired route diagnostics and beta issue reports."

    def handle(self, *args, **options):
        diagnostics_before = RouteDiagnostic.objects.count()
        reports_before = RouteIssueReport.objects.count()
        exact_before = RouteIssueReport.objects.exclude(
            consented_location_data={}
        ).count()
        purge_expired_beta_records()
        diagnostics_deleted = diagnostics_before - RouteDiagnostic.objects.count()
        reports_deleted = reports_before - RouteIssueReport.objects.count()
        exact_purged = exact_before - RouteIssueReport.objects.exclude(
            consented_location_data={}
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {diagnostics_deleted} diagnostics and "
                f"{reports_deleted} reports; purged exact data from "
                f"{exact_purged} reports."
            )
        )
