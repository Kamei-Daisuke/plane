"""Re-activate tabata's keis membership + verify kobayashi.

tabata left both workspaces (is_active=False on keis and os-reiji-tabata),
so login lands on create-workspace. Flip the keis membership back to active
so they return to the real workspace. Also verify the backfilled kobayashi
membership is active.

Run inside the API container:
  sudo docker exec -i <api-container> python manage.py shell < /tmp/fix_tabata_keis_active.py
"""

from plane.db.models import User, Workspace, WorkspaceMember

keis = Workspace.objects.get(slug="keis")

# 1. Re-activate tabata on keis
tabata = User.objects.get(email="reiji.tabata@keis-software.com")
wm = WorkspaceMember.objects.get(member=tabata, workspace=keis)
wm.is_active = True
wm.save(update_fields=["is_active"])
print(f"tabata keis is_active -> {wm.is_active} role={wm.role}")

# 2. Verify kobayashi (backfilled) is active on keis
kob = User.objects.filter(email="satoshi.kobayashi@keis-software.com").first()
if not kob:
    print("kobayashi: user not found")
else:
    k_wm = WorkspaceMember.objects.filter(member=kob, workspace=keis).first()
    if k_wm:
        print(f"kobayashi keis is_active={k_wm.is_active} role={k_wm.role}")
    else:
        print("kobayashi: NO keis membership")
