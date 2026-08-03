from django.db import migrations


class Migration(migrations.Migration):
    """Compatibility migration for databases that reached migration 0005.

    Trip cancellation was removed before release, so this migration deliberately
    performs no schema operation while preserving the migration graph.
    """

    dependencies = [
        ("trips", "0004_trip_on_duty_hours"),
    ]

    operations = []