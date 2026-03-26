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
SECRETS_URL="https://raw.githubusercontent.com/Kamei-Daisuke/plane-ops/main/secrets.env"
SECRETS_FILE=""

echo "============================================"
echo "  Plane — Lightsail Setup"
echo "============================================"
echo ""

# ----- Try to fetch secrets from private repo -----
try_fetch_secrets() {
  echo "[*] Checking for secrets in plane-ops (private repo)..."

  # Try with gh CLI token
  local token=""
  if command -v gh &>/dev/null; then
    token=$(gh auth token 2>/dev/null || true)
  fi

  # Try with GITHUB_TOKEN env var
  if [ -z "$token" ] && [ -n "${GITHUB_TOKEN:-}" ]; then
    token="$GITHUB_TOKEN"
  fi

  if [ -n "$token" ]; then
    local tmpfile
    tmpfile=$(mktemp)
    if curl -fsSL -H "Authorization: token $token" "$SECRETS_URL" -o "$tmpfile" 2>/dev/null; then
      SECRETS_FILE="$tmpfile"
      # shellcheck disable=SC1090
      source "$SECRETS_FILE"
      echo "[OK] Secrets loaded from plane-ops. Interactive prompts will be skipped."
      return 0
    fi
    rm -f "$tmpfile"
  fi

  echo "[!] Could not fetch secrets (no access to plane-ops). Will prompt for values."
  return 1
}

try_fetch_secrets || true

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
  mkdir -p "$PLANE_DIR/apps/api" "$PLANE_DIR/proxy-config"

  curl -fsSL "$REPO_RAW/docker-compose.deploy.yml" -o "$PLANE_DIR/docker-compose.deploy.yml"
  curl -fsSL "$REPO_RAW/.env.deploy.example"       -o "$PLANE_DIR/.env.deploy.example"
  curl -fsSL "$REPO_RAW/.env.deploy.api.example"    -o "$PLANE_DIR/.env.deploy.api.example"

  # Copy examples if .env files don't exist yet
  [ -f "$PLANE_DIR/.env" ]          || cp "$PLANE_DIR/.env.deploy.example"     "$PLANE_DIR/.env"
  [ -f "$PLANE_DIR/apps/api/.env" ] || cp "$PLANE_DIR/.env.deploy.api.example" "$PLANE_DIR/apps/api/.env"

  echo "[OK] Files downloaded to $PLANE_DIR"
}

generate_secrets() {
  local pg_pass secret_key live_secret
  pg_pass=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 20)
  secret_key=$(openssl rand -hex 32)
  live_secret=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9' | head -c 32)

  # .env
  sed -i "s|POSTGRES_PASSWORD=plane|POSTGRES_PASSWORD=$pg_pass|g" "$PLANE_DIR/.env"

  # apps/api/.env
  sed -i "s|POSTGRES_PASSWORD=plane|POSTGRES_PASSWORD=$pg_pass|g"                     "$PLANE_DIR/apps/api/.env"
  sed -i "s|SECRET_KEY=$|SECRET_KEY=$secret_key|g"                                    "$PLANE_DIR/apps/api/.env"
  sed -i "s|LIVE_SERVER_SECRET_KEY=secret-key|LIVE_SERVER_SECRET_KEY=$live_secret|g"   "$PLANE_DIR/apps/api/.env"
  sed -i "s|DATABASE_URL=postgresql://plane:plane@|DATABASE_URL=postgresql://plane:$pg_pass@|g" "$PLANE_DIR/apps/api/.env"

  echo "[OK] Random secrets generated (DB password, SECRET_KEY, LIVE_SERVER_SECRET_KEY)."
}

configure_s3() {
  echo ""
  echo "=== S3 Configuration ==="

  local s3_key="${S3_ACCESS_KEY_ID:-}"
  local s3_secret="${S3_SECRET_ACCESS_KEY:-}"
  local s3_bucket="${S3_BUCKET_NAME:-}"
  local aws_region="${S3_REGION:-}"

  if [ -z "$s3_key" ]; then
    echo "Plane uses S3 for file storage. You need an IAM user with S3 access."
    echo ""
    read -rp "AWS S3 Access Key ID: " s3_key
    read -rsp "AWS S3 Secret Access Key: " s3_secret
    echo ""
    read -rp "S3 Bucket Name [plane-keis-uploads]: " s3_bucket
    read -rp "AWS Region [ap-northeast-1]: " aws_region
  fi

  s3_bucket="${s3_bucket:-plane-keis-uploads}"
  aws_region="${aws_region:-ap-northeast-1}"

  sed -i "s|AWS_ACCESS_KEY_ID=$|AWS_ACCESS_KEY_ID=$s3_key|g"           "$PLANE_DIR/apps/api/.env"
  sed -i "s|AWS_SECRET_ACCESS_KEY=$|AWS_SECRET_ACCESS_KEY=$s3_secret|g" "$PLANE_DIR/apps/api/.env"
  sed -i "s|AWS_S3_BUCKET_NAME=plane-keis-uploads|AWS_S3_BUCKET_NAME=$s3_bucket|g" "$PLANE_DIR/apps/api/.env"
  sed -i "s|AWS_REGION=ap-northeast-1|AWS_REGION=$aws_region|g"         "$PLANE_DIR/apps/api/.env"

  echo "[OK] S3 configured: bucket=$s3_bucket, region=$aws_region"
}

configure_urls() {
  echo ""
  echo "=== Domain / URL Configuration ==="

  local site_addr="${SITE_DOMAIN:-}"
  local cert_email="${CERT_EMAIL:-}"

  if [ -z "$site_addr" ]; then
    read -rp "Enter your domain or public IP (e.g. plane.example.com or 1.2.3.4): " site_addr
  fi

  if [ -z "$site_addr" ]; then
    echo "[!] No address provided. Using :80 (HTTP on all interfaces)"
    site_addr=":80"
    base_url="http://localhost"
  elif [[ "$site_addr" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    # IP address — HTTP only
    base_url="http://$site_addr"
  else
    # Domain — HTTPS with Route53 DNS challenge
    sed -i "s|SITE_ADDRESS=:80|SITE_ADDRESS=$site_addr|g" "$PLANE_DIR/.env"
    base_url="https://$site_addr"

    if [ -z "$cert_email" ]; then
      read -rp "Email for Let's Encrypt certificate: " cert_email
    fi
    if [ -n "$cert_email" ]; then
      echo "CERT_EMAIL=$cert_email" >> "$PLANE_DIR/.env"
    fi

    local r53_key="${R53_ACCESS_KEY_ID:-}"
    local r53_secret="${R53_SECRET_ACCESS_KEY:-}"
    local r53_zone="${R53_HOSTED_ZONE_ID:-}"

    if [ -z "$r53_key" ]; then
      echo ""
      echo "=== Route53 DNS Challenge (for HTTPS) ==="
      echo "Required for automatic HTTPS without opening ports to the internet."
      echo "Use a dedicated IAM user with Route53 ChangeResourceRecordSets permission."
      echo ""
      read -rp "Route53 AWS Access Key ID: " r53_key
      read -rsp "Route53 AWS Secret Access Key: " r53_secret
      echo ""
      read -rp "Route53 Hosted Zone ID: " r53_zone
    fi

    echo "PROXY_AWS_ACCESS_KEY_ID=$r53_key"       >> "$PLANE_DIR/.env"
    echo "PROXY_AWS_SECRET_ACCESS_KEY=$r53_secret" >> "$PLANE_DIR/.env"
    echo "ROUTE53_HOSTED_ZONE_ID=$r53_zone"       >> "$PLANE_DIR/.env"

    # Create Caddyfile with Route53 DNS challenge
    cat > "$PLANE_DIR/proxy-config/Caddyfile" <<'CADDYEOF'
{
	acme_ca {$CERT_ACME_CA:https://acme-v02.api.letsencrypt.org/directory}
	servers {
		max_header_size 25MB
		client_ip_headers X-Forwarded-For X-Real-IP
		trusted_proxies static {$TRUSTED_PROXIES:0.0.0.0/0}
	}
}

(plane_proxy) {
	request_body {
		max_size {$FILE_SIZE_LIMIT}
	}

	redir /spaces /spaces/ permanent
	reverse_proxy /spaces/* space:3000

	redir /god-mode /god-mode/ permanent
	reverse_proxy /god-mode/* admin:3000

	reverse_proxy /live/* live:3000
	reverse_proxy /api/* api:8000
	reverse_proxy /auth/* api:8000
	reverse_proxy /static/* api:8000

	reverse_proxy /* web:3000
}

{$SITE_ADDRESS} {
	tls {$CERT_EMAIL} {
		dns route53 {
			region {$ROUTE53_AWS_REGION:ap-northeast-1}
			access_key_id {$ROUTE53_ACCESS_KEY_ID}
			secret_access_key {$ROUTE53_SECRET_ACCESS_KEY}
			hosted_zone_id {$ROUTE53_HOSTED_ZONE_ID}
		}
	}
	import plane_proxy
}
CADDYEOF

    # Add Caddyfile volume mount to compose if not present
    if ! grep -q 'proxy-config/Caddyfile' "$PLANE_DIR/docker-compose.deploy.yml"; then
      sed -i '/caddy_data:\/data/a\      - ./proxy-config/Caddyfile:/etc/caddy/Caddyfile:ro' "$PLANE_DIR/docker-compose.deploy.yml"
    fi

    echo "[OK] Route53 DNS challenge configured."
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
  echo "=== GitHub Container Registry ==="

  local gh_user="${GHCR_USER:-}"
  local gh_pat=""

  # Try gh CLI token first
  if command -v gh &>/dev/null; then
    gh_pat=$(gh auth token 2>/dev/null || true)
  fi
  if [ -z "$gh_pat" ] && [ -n "${GITHUB_TOKEN:-}" ]; then
    gh_pat="$GITHUB_TOKEN"
  fi

  if [ -z "$gh_pat" ]; then
    echo "Create a PAT at: https://github.com/settings/tokens"
    echo "  -> Scope: read:packages"
    echo ""
    read -rp "GitHub username [Kamei-Daisuke]: " gh_user
    read -rsp "GitHub PAT: " gh_pat
    echo ""
  fi

  gh_user="${gh_user:-Kamei-Daisuke}"
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
  echo "  Initial startup may take 5-10 minutes on 1GB instances."
  echo "  Run 'docker compose -f docker-compose.deploy.yml ps' to check status."
  echo ""
  echo "  After initial setup, you can stop Admin to save memory:"
  echo "    docker compose -f docker-compose.deploy.yml stop admin"
  echo "============================================"
}

# ----- Main -----
install_docker
install_compose
setup_swap
download_files
generate_secrets
configure_s3
configure_urls
login_ghcr
start_plane
