from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nonconformites", "0002_nonconformite_site_nullable"),
    ]

    operations = [
        migrations.AddField(
            model_name="nonconformite",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="nonconformites/"),
        ),
    ]
