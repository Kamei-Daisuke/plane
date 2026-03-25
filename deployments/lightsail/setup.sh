#!/bin/bash
set -euo pipefail

# =============================================================
# Plane — Lightsail one-shot setup script
# Tested on: Amazon Linux 2023 / Ubuntu 22.04
# Usage:
#   1. Create a Lightsail instance (1 GB+ RAM)
#   2. SSH in and run:
#        curl -fsSL https://raw.githubusercontent.com/Kamei-Daisuke/plane/keis/deployments/lightsail/setup.sh | bash
#   3. Follow the prompts
# =============================================================

PLANE_DIR="$HOME/plane"
REPO_RAW="https://raw.githubusercontent.com/Kamei-Daisuke/plane/keis"

echo "============================================"
echo "  Plane — Lightsail Setup"
echo "============================================"
echo ""

# ----- Detect OS & install Docker -----
install_docker() {
  if command -v docker &>/dev/null; then
    echo "[OK] Docker is already installed."
    return
  fi

  echo "[*] Installing Docker..."
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    case "$ID" in
      amzn)
        sudo yum install -y docker
        ;;
      ubuntu|debian)
        sudo apt-get update -y
        sudo apt-get install -y docker.io
        ;;
      *)
        echo "[!] Unsupported OS: $ID — installing via get.docker.com"
        curl -fsSL https://get.docker.com | sudo sh
        ;;
    esac
  else
    curl -fsSL https://get.docker.com | sudo sh
  fi

  sudo systemctl enable --now docker
  sudo usermod -aG docker "$USER"
  echo "[OK] Docker installed. You may need to re-login for group changes."
}

install_compose() {
  if docker compose version &>/dev/null; then
    echo "[OK] Docker Compose plugin is already installed."
    return
  fi

  echo "[*] Installing Docker Compose plugin..."
  sudo mkdir -p /usr/local/lib/docker/cli-plugins
  sudo curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
  sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  echo "[OK] Docker Compose installed."
}

setup_swap() {
  if swapon --show | grep -q '/swapfile'; then
    echo "[OK] Swap already configured."
    return
  fi

  echo "[*] Creating 1GB swap (recommended for 1GB instances)..."
  sudo fallocate -l 1G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile

  # Persist on reboot
  if ! grep -q '/swapfile' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  fi
  echo "[OK] 1GB swap enabled."
}

download_files() {
  echo "[*] Setting up $PLANE_DIR ..."
  mkdir -p "$PLANE_DIR/apps/api"

  curl -fsSL "$REPO_RAW/docker-compose.deploy.yml" -o "$PLANE_DIR/docker-compose.deploy.yml"
  curl -fsSL "$REPO_RAW/.env.deploy.example"       -o "$PLANE_DIR/.env.deploy.example"
  curl -fsSL "$REPO_RAW/.env.deploy.api.example"    -o "$PLANE_DIR/.env.deploy.api.example"

  # Copy examples if .env files don't exist yet
  [ -f "$PLANE_DIR/.env" ]          || cp "$PLANE_DIR/.env.deploy.example"     "$PLANE_DIR/.env"
  [ -f "$PLANE_DIR/apps/api/.env" ] || cp "$PLANE_DIR/.env.deploy.api.example" "$PLANE_DIR/apps/api/.env"

  echo "[OK] Files downloaded to $PLANE_DIR"
}

generate_secrets() {
  # Generate random passwords if still using defaults
  local pg_pass
  pg_pass=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)
  local mq_pass
  mq_pass=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)
  local minio_key
  minio_key=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)
  local minio_secret
  minio_secret=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)
  local live_secret
  live_secret=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)

  # .env
  sed -i "s|POSTGRES_PASSWORD=plane|POSTGRES_PASSWORD=$pg_pass|g"       "$PLANE_DIR/.env"
  sed -i "s|RABBITMQ_PASSWORD=plane|RABBITMQ_PASSWORD=$mq_pass|g"      "$PLANE_DIR/.env"
  sed -i "s|AWS_ACCESS_KEY_ID=access-key|AWS_ACCESS_KEY_ID=$minio_key|g"         "$PLANE_DIR/.env"
  sed -i "s|AWS_SECRET_ACCESS_KEY=secret-key|AWS_SECRET_ACCESS_KEY=$minio_secret|g" "$PLANE_DIR/.env"

  # apps/api/.env
  sed -i "s|POSTGRES_PASSWORD=plane|POSTGRES_PASSWORD=$pg_pass|g"       "$PLANE_DIR/apps/api/.env"
  sed -i "s|RABBITMQ_PASSWORD=plane|RABBITMQ_PASSWORD=$mq_pass|g"      "$PLANE_DIR/apps/api/.env"
  sed -i "s|AWS_ACCESS_KEY_ID=access-key|AWS_ACCESS_KEY_ID=$minio_key|g"         "$PLANE_DIR/apps/api/.env"
  sed -i "s|AWS_SECRET_ACCESS_KEY=secret-key|AWS_SECRET_ACCESS_KEY=$minio_secret|g" "$PLANE_DIR/apps/api/.env"
  sed -i "s|LIVE_SERVER_SECRET_KEY=secret-key|LIVE_SERVER_SECRET_KEY=$live_secret|g" "$PLANE_DIR/apps/api/.env"

  # Fix DATABASE_URL with new password
  sed -i "s|DATABASE_URL=postgresql://plane:plane@|DATABASE_URL=postgresql://plane:$pg_pass@|g" "$PLANE_DIR/apps/api/.env"

  echo "[OK] Random secrets generated."
}

configure_urls() {
  echo ""
  read -rp "Enter your domain or public IP (e.g. plane.example.com or 1.2.3.4): " site_addr

  if [ -z "$site_addr" ]; then
    echo "[!] No address provided. Using :80 (HTTP on all interfaces)"
    site_addr=":80"
    base_url="http://localhost"
  else
    # If it looks like an IP, use http://IP
    if [[ "$site_addr" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      sed -i "s|SITE_ADDRESS=:80|SITE_ADDRESS=:80|g" "$PLANE_DIR/.env"
      base_url="http://$site_addr"
    else
      # Domain — use HTTPS
      sed -i "s|SITE_ADDRESS=:80|SITE_ADDRESS=$site_addr|g" "$PLANE_DIR/.env"
      read -rp "Email for Let's Encrypt SSL certificate: " cert_email
      if [ -n "$cert_email" ]; then
        sed -i "s|# CERT_EMAIL=email you@example.com|CERT_EMAIL=email $cert_email|g" "$PLANE_DIR/.env"
        sed -i "s|CERT_EMAIL=$|CERT_EMAIL=email $cert_email|g" "$PLANE_DIR/.env"
      fi
      base_url="https://$site_addr"
    fi
  fi

  # Update API .env URLs
  sed -i "s|WEB_URL=http://localhost|WEB_URL=$base_url|g"         "$PLANE_DIR/apps/api/.env"
  sed -i "s|ADMIN_BASE_URL=http://localhost|ADMIN_BASE_URL=$base_url|g" "$PLANE_DIR/apps/api/.env"
  sed -i "s|SPACE_BASE_URL=http://localhost|SPACE_BASE_URL=$base_url|g" "$PLANE_DIR/apps/api/.env"
  sed -i "s|APP_BASE_URL=http://localhost|APP_BASE_URL=$base_url|g"     "$PLANE_DIR/apps/api/.env"
  sed -i "s|LIVE_BASE_URL=http://localhost|LIVE_BASE_URL=$base_url|g"   "$PLANE_DIR/apps/api/.env"

  echo "[OK] URLs configured: $base_url"
}

login_ghcr() {
  echo ""
  echo "GitHub Container Registry login required."
  echo "Create a PAT at: https://github.com/settings/tokens"
  echo "  -> Scope: read:packages"
  echo ""
  read -rp "GitHub username [Kamei-Daisuke]: " gh_user
  gh_user="${gh_user:-Kamei-Daisuke}"
  read -rsp "GitHub PAT: " gh_pat
  echo ""

  echo "$gh_pat" | docker login ghcr.io -u "$gh_user" --password-stdin
  echo "[OK] Logged in to ghcr.io"
}

start_plane() {
  echo ""
  echo "[*] Pulling images and starting Plane..."
  cd "$PLANE_DIR"
  docker compose -f docker-compose.deploy.yml pull
  docker compose -f docker-compose.deploy.yml up -d

  echo ""
  echo "============================================"
  echo "  Plane is starting up!"
  echo "============================================"
  echo ""
  echo "  URL: $base_url"
  echo "  Logs: cd $PLANE_DIR && docker compose -f docker-compose.deploy.yml logs -f"
  echo ""
  echo "  Initial startup may take 1-2 minutes."
  echo "  Run 'docker compose -f docker-compose.deploy.yml ps' to check status."
  echo "============================================"
}

# ----- Main -----
install_docker
install_compose
setup_swap
download_files
generate_secrets
configure_urls
login_ghcr
start_plane
