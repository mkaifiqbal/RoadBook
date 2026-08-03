from django.db import migrations, models


def backfill_on_duty_hours(apps, schema_editor):
    Trip = apps.get_model("trips", "Trip")
    for trip in Trip.objects.iterator():
        summary = (trip.plan or {}).get("summary", {})
        trip.on_duty_hours = round(
            float(summary.get("driving_hours", trip.driving_hours) or 0)
            + float(summary.get("on_duty_not_driving_hours", 0) or 0),
            2,
        )
        trip.save(update_fields=["on_duty_hours"])


class Migration(migrations.Migration):
    dependencies = [("trips", "0003_seed_demo_accounts")]

    operations = [
        migrations.AddField(
            model_name="trip",
            name="on_duty_hours",
            field=models.FloatField(
                default=0,
                help_text="Total driving plus on-duty-not-driving hours for this trip.",
            ),
        ),
        migrations.RunPython(backfill_on_duty_hours, migrations.RunPython.noop),
    ]