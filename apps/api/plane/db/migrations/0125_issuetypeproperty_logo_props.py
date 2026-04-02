# Generated migration for logo_props field on IssueTypeProperty

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("db", "0124_worklog_indices"),
    ]

    operations = [
        migrations.AddField(
            model_name="issuetypeproperty",
            name="logo_props",
            field=models.JSONField(default=dict),
        ),
    ]
