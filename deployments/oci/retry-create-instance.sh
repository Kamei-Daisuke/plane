#!/bin/bash
# Retry OCI ARM instance creation until successful
# Usage: nohup bash deployments/oci/retry-create-instance.sh &

set -uo pipefail
export SUPPRESS_LABEL_WARNING=True

OCI="$HOME/bin/oci"
TENANCY="ocid1.tenancy.oc1..aaaaaaaamrs3sijaylxumycz4s2cbifcttxq6xwuuqc45e3x7qoi3x36efpq"
AD="mqJO:AP-TOKYO-1-AD-1"
IMAGE="ocid1.image.oc1.ap-tokyo-1.aaaaaaaasvetlwst34qdqee3uz5jgbu2p4fqfut6ad3maarfwt5zutwwwr5q"
SUBNET="ocid1.subnet.oc1.ap-tokyo-1.aaaaaaaaeggk7qxg6x4pa7fxfrlxtpgnah63a6pzuiwm6orhcc2x2z44ytdq"
SSH_KEY_FILE="$HOME/.ssh/oci-plane.pub"
LOG_FILE="$HOME/oci-retry.log"

OCPUS=4
MEMORY_GB=25
INTERVAL=60  # 5 minutes

echo "$(date): Starting retry loop (${OCPUS} OCPU / ${MEMORY_GB}GB, every ${INTERVAL}s)" | tee -a "$LOG_FILE"

while true; do
  RESULT=$($OCI compute instance launch \
    --compartment-id "$TENANCY" \
    --availability-domain "$AD" \
    --shape "VM.Standard.A1.Flex" \
    --shape-config "{\"ocpus\":${OCPUS},\"memoryInGBs\":${MEMORY_GB}}" \
    --image-id "$IMAGE" \
    --subnet-id "$SUBNET" \
    --assign-public-ip true \
    --display-name "plane" \
    --ssh-authorized-keys-file "$SSH_KEY_FILE" \
    --boot-volume-size-in-gbs 50 2>&1)

  if echo "$RESULT" | grep -q '"lifecycle-state"'; then
    echo "$(date): SUCCESS! Instance created." | tee -a "$LOG_FILE"
    echo "$RESULT" | tee -a "$LOG_FILE"

    # Extract public IP
    INSTANCE_ID=$(echo "$RESULT" | grep -o '"id": "[^"]*"' | head -1 | cut -d'"' -f4)
    sleep 30
    PUBLIC_IP=$($OCI compute instance list-vnics --instance-id "$INSTANCE_ID" --query "data[0].\"public-ip\"" --raw-output 2>/dev/null)
    echo "$(date): Public IP: $PUBLIC_IP" | tee -a "$LOG_FILE"

    # Signal success
    touch "$HOME/oci-instance-created"
    echo "$PUBLIC_IP" > "$HOME/oci-instance-ip"
    exit 0
  else
    echo "$(date): Failed (Out of capacity). Retrying in ${INTERVAL}s..." | tee -a "$LOG_FILE"
    sleep $INTERVAL
  fi
done
