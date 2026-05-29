"""Disable workspace creation for regular users (DISABLE_WORKSPACE_CREATION=1).

get_configuration_value reads the InstanceConfiguration table first (SKIP_ENV_VAR=1),
so flipping the env alone is not enough once the key exists in the DB — we update
the row directly. Idempotent.

Run inside the API container:
  sudo docker exec -i <api-container> python manage.py shell < /tmp/disable_workspace_creation.py
"""

from plane.license.models import InstanceConfiguration

obj, created = InstanceConfiguration.objects.get_or_create(
    key="DISABLE_WORKSPACE_CREATION",
    defaults={"value": "1", "category": "WORKSPACE"},
)
if not created and obj.value != "1":
    obj.value = "1"
    obj.save(update_fields=["value"])

print(f"DISABLE_WORKSPACE_CREATION = {obj.value} (created={created})")
