from django.contrib.auth.hashers import make_password
from django.db import migrations


DEMO_ACCOUNTS = (
    {
        "email": "admin@roadbook.demo",
        "password": "RoadbookAdmin!2026",
        "first_name": "Morgan",
        "last_name": "Reed",
        "role": "admin",
        "is_staff": True,
        "is_superuser": True,
        "truck_number": "",
    },
    {
        "email": "driver@roadbook.demo",
        "password": "RoadbookDriver!2026",
        "first_name": "Jordan",
        "last_name": "Ellis",
        "role": "driver",
        "is_staff": False,
        "is_superuser": False,
        "truck_number": "TRK-204",
    },
)


def seed_demo_accounts(apps, schema_editor):
    User = apps.get_model("auth", "User")
    DriverProfile = apps.get_model("trips", "DriverProfile")

    for account in DEMO_ACCOUNTS:
        user, _ = User.objects.update_or_create(
            username=account["email"],
            defaults={
                "email": account["email"],
                "first_name": account["first_name"],
                "last_name": account["last_name"],
                "password": make_password(account["password"]),
                "is_active": True,
                "is_staff": account["is_staff"],
                "is_superuser": account["is_superuser"],
            },
        )
        DriverProfile.objects.update_or_create(
            user=user,
            defaults={
                "role": account["role"],
                "status": "active",
                "truck_number": account["truck_number"],
                "carrier_name": "Northline Freight",
            },
        )


def remove_demo_accounts(apps, schema_editor):
    User = apps.get_model("auth", "User")
    User.objects.filter(username__in=[account["email"] for account in DEMO_ACCOUNTS]).delete()


class Migration(migrations.Migration):
    dependencies = [("trips", "0002_trip_driver_driverprofile")]
    operations = [migrations.RunPython(seed_demo_accounts, remove_demo_accounts)]