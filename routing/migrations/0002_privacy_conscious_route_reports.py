from datetime import timedelta
import uuid

from django.db import migrations, models
from django.utils import timezone


def migrate_existing_beta_data(apps, schema_editor):
    RouteDiagnostic = apps.get_model("routing", "RouteDiagnostic")
    for diagnostic in RouteDiagnostic.objects.iterator():
        route = diagnostic.route_payload if isinstance(diagnostic.route_payload, dict) else {}
        validation = (
            diagnostic.exact_diagnostics
            if isinstance(diagnostic.exact_diagnostics, dict)
            else {}
        )
        diagnostic.vehicle_profile = ""
        diagnostic.waypoint_count = len(
            diagnostic.request_payload.get("waypoints", [])
            if isinstance(diagnostic.request_payload, dict)
            else []
        )
        diagnostic.response_summary = {
            "distanceMetres": route.get("distanceMetres"),
            "durationSeconds": route.get("durationSeconds"),
            "polylinePointCount": len(route.get("polyline", [])),
            "legCount": len(route.get("legs", [])),
            "endpointSnaps": {
                "start": validation.get("startSnapBand"),
                "destination": validation.get("destinationSnapBand"),
            },
        }
        diagnostic.save(
            update_fields=["vehicle_profile", "waypoint_count", "response_summary"]
        )

    RouteIssueReport = apps.get_model("routing", "RouteIssueReport")
    for report in RouteIssueReport.objects.iterator():
        metadata = report.metadata if isinstance(report.metadata, dict) else {}
        client_metadata = metadata.get("client", {})
        report.reporter_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"rallyify-legacy-report:{report.reporter_fingerprint}",
        )
        report.idempotency_key = f"legacy-{report.dedupe_key}"
        report.payload_fingerprint = report.dedupe_key
        report.graph_version = (
            client_metadata.get("graphBuildId", "")
            if isinstance(client_metadata, dict)
            else ""
        )
        report.summary_expires_at = report.created_at + timedelta(days=90)
        if report.consented_location_data:
            report.exact_data_expires_at = report.created_at + timedelta(days=30)
        report.save(
            update_fields=[
                "reporter_id",
                "idempotency_key",
                "payload_fingerprint",
                "graph_version",
                "summary_expires_at",
                "exact_data_expires_at",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [("routing", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="routediagnostic",
            name="vehicle_profile",
            field=models.CharField(default="", max_length=50),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="routediagnostic",
            name="waypoint_count",
            field=models.PositiveSmallIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="routediagnostic",
            name="response_summary",
            field=models.JSONField(default=dict),
        ),
        migrations.RenameField(
            model_name="routeissuereport",
            old_name="expires_at",
            new_name="summary_expires_at",
        ),
        migrations.AddField(
            model_name="routeissuereport",
            name="reporter_id",
            field=models.UUIDField(db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="routeissuereport",
            name="idempotency_key",
            field=models.CharField(blank=True, editable=False, max_length=100),
        ),
        migrations.AddField(
            model_name="routeissuereport",
            name="payload_fingerprint",
            field=models.CharField(blank=True, editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name="routeissuereport",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("triaged", "Triaged"),
                    ("investigating", "Investigating"),
                    ("resolved", "Resolved"),
                    ("rejected", "Rejected"),
                ],
                db_index=True,
                default="new",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="routeissuereport",
            name="graph_version",
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AddField(
            model_name="routeissuereport",
            name="internal_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="routeissuereport",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="routeissuereport",
            name="exact_data_expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="routeissuereport",
            name="exact_data_purged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(migrate_existing_beta_data, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="routediagnostic",
            name="request_payload",
        ),
        migrations.RemoveField(
            model_name="routediagnostic",
            name="route_payload",
        ),
        migrations.RemoveField(
            model_name="routediagnostic",
            name="exact_diagnostics",
        ),
        migrations.RemoveField(
            model_name="routeissuereport",
            name="reporter_fingerprint",
        ),
        migrations.RemoveField(
            model_name="routeissuereport",
            name="dedupe_key",
        ),
        migrations.AlterField(
            model_name="routeissuereport",
            name="reporter_id",
            field=models.UUIDField(db_index=True, editable=False),
        ),
        migrations.AlterField(
            model_name="routeissuereport",
            name="idempotency_key",
            field=models.CharField(editable=False, max_length=100),
        ),
        migrations.AlterField(
            model_name="routeissuereport",
            name="payload_fingerprint",
            field=models.CharField(editable=False, max_length=64),
        ),
        migrations.AlterField(
            model_name="routeissuereport",
            name="category",
            field=models.CharField(db_index=True, max_length=50),
        ),
        migrations.AddConstraint(
            model_name="routeissuereport",
            constraint=models.UniqueConstraint(
                fields=("reporter_id", "idempotency_key"),
                name="unique_route_report_idempotency_per_user",
            ),
        ),
        migrations.AddIndex(
            model_name="routeissuereport",
            index=models.Index(
                fields=["status", "created_at"],
                name="routing_rou_status_3cbdff_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="routeissuereport",
            index=models.Index(
                fields=["category", "created_at"],
                name="routing_rou_categor_f9072a_idx",
            ),
        ),
    ]
