# Plane デプロイガイド（AWS Lightsail）

## 概要

AWS Lightsail micro ($7/月・1GB RAM) に Plane をデプロイする手順。
GHCR のビルド済みイメージを使い、HTTPS は Route53 DNS チャレンジで Let's Encrypt 証明書を自動取得する。

秘密情報は AWS SSM Parameter Store（`/plane/*`）で管理。具体的な値は SSM を参照。

---

## 前提

- AWS CLI に対象アカウントのプロファイルが設定済み
- GitHub PAT（`read:packages` 権限）を取得済み
- ドメインの DNS が Route53 で管理されている

## 現在のインフラ情報

| 項目                    | 値                                               |
| ----------------------- | ------------------------------------------------ |
| インスタンス名          | `plane`                                          |
| 静的 IP                 | SSM 参照 or `aws lightsail get-static-ip` で確認 |
| ドメイン                | SSM `/plane/site-domain`                         |
| Route53 ホストゾーン ID | SSM `/plane/r53-hosted-zone-id`                  |
| リージョン              | ap-northeast-1 (東京)                            |
| OS                      | Amazon Linux 2023                                |

---

## 1. インスタンス作成

```bash
PROFILE=keis
REGION=ap-northeast-1

# インスタンス作成（Amazon Linux 2023, micro: 1GB RAM）
aws lightsail create-instances --profile $PROFILE --region $REGION \
  --instance-names plane \
  --availability-zone ${REGION}a \
  --blueprint-id amazon_linux_2023 \
  --bundle-id micro_3_0

# 静的 IP を割り当て＆アタッチ
aws lightsail allocate-static-ip --profile $PROFILE --region $REGION \
  --static-ip-name plane-ip
aws lightsail attach-static-ip --profile $PROFILE --region $REGION \
  --static-ip-name plane-ip --instance-name plane

# ファイアウォール設定（特定 IP のみ許可）
MY_IP=$(curl -s ifconfig.io)
aws lightsail put-instance-public-ports --profile $PROFILE --region $REGION \
  --instance-name plane \
  --port-infos "[
    {\"fromPort\":22,\"toPort\":22,\"protocol\":\"tcp\",\"cidrs\":[\"${MY_IP}/32\"]},
    {\"fromPort\":80,\"toPort\":80,\"protocol\":\"tcp\",\"cidrs\":[\"${MY_IP}/32\"]},
    {\"fromPort\":443,\"toPort\":443,\"protocol\":\"tcp\",\"cidrs\":[\"${MY_IP}/32\"]}
  ]"

# 静的 IP を確認
aws lightsail get-static-ip --profile $PROFILE --region $REGION \
  --static-ip-name plane-ip --query "staticIp.ipAddress" --output text
```

## 2. SSH 接続

```bash
STATIC_IP=$(aws lightsail get-static-ip --profile $PROFILE --region $REGION \
  --static-ip-name plane-ip --query "staticIp.ipAddress" --output text)

# デフォルトキーペアを使う場合
aws lightsail download-default-key-pair --profile $PROFILE --region $REGION \
  --query "privateKeyBase64" --output text > ~/.ssh/lightsail-plane.pem
chmod 600 ~/.ssh/lightsail-plane.pem
ssh -i ~/.ssh/lightsail-plane.pem ec2-user@$STATIC_IP
```

### SSH ユーザー

| ユーザー | 鍵                           | sudo            |
| -------- | ---------------------------- | --------------- |
| ec2-user | Lightsail デフォルトキーペア | あり            |
| kamei    | keis-kamei.pem               | あり (NOPASSWD) |
| sayama   | sayama.pem                   | あり (NOPASSWD) |

## 3. ワンコマンドセットアップ

```bash
curl -fsSL https://raw.githubusercontent.com/Kamei-Daisuke/plane/keis/deployments/lightsail/setup.sh | bash
```

スクリプトが以下を自動で行う：

- Docker / Docker Compose インストール
- 1GB スワップ作成
- デプロイファイルのダウンロード
- ランダムパスワード生成（DB パスワード、SECRET_KEY、LIVE_SERVER_SECRET_KEY）
- SSM Parameter Store からシークレット自動取得（AWS CLI がある場合）
  - S3 認証情報、Route53 認証情報、ドメイン、メール等
  - AWS CLI がない場合は対話式にフォールバック
- Caddyfile 生成（Route53 DNS チャレンジ対応）
- GHCR ログイン → イメージ pull → 起動

## 4. 手動セットアップ

### 4.1 Docker インストール

```bash
sudo yum install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# Docker Compose plugin
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
```

### 4.2 スワップ作成（1GB インスタンスでは必須）

```bash
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 4.3 ファイル配置

```bash
mkdir -p ~/plane/apps/api ~/plane/proxy-config
cd ~/plane

REPO_RAW="https://raw.githubusercontent.com/Kamei-Daisuke/plane/keis"
curl -fsSL "$REPO_RAW/docker-compose.deploy.yml" -o docker-compose.deploy.yml
curl -fsSL "$REPO_RAW/.env.deploy.example" -o .env
curl -fsSL "$REPO_RAW/.env.deploy.api.example" -o apps/api/.env
```

### 4.4 環境変数の設定

`.env` と `apps/api/.env` を編集する。特に以下が重要：

| 変数                          | ファイル        | 説明                                              | setup.sh           |
| ----------------------------- | --------------- | ------------------------------------------------- | ------------------ |
| `POSTGRES_PASSWORD`           | 両方            | DB パスワード                                     | 自動生成           |
| `SECRET_KEY`                  | `apps/api/.env` | Django SECRET_KEY（**必須**）                     | 自動生成           |
| `AMQP_URL`                    | `apps/api/.env` | Celery ブローカー（`redis://plane-redis:6379/1`） | テンプレに設定済み |
| `DATABASE_URL`                | `apps/api/.env` | DB 接続 URL                                       | 自動生成           |
| `AWS_ACCESS_KEY_ID`           | `apps/api/.env` | S3 用 IAM キー                                    | SSM から取得       |
| `AWS_SECRET_ACCESS_KEY`       | `apps/api/.env` | S3 用 IAM シークレット                            | SSM から取得       |
| `WEB_URL` 等                  | `apps/api/.env` | アプリ URL                                        | SSM/対話で設定     |
| `SITE_ADDRESS`                | `.env`          | Caddy のリッスンドメイン                          | SSM/対話で設定     |
| `CERT_EMAIL`                  | `.env`          | Let's Encrypt メール                              | SSM/対話で設定     |
| `PROXY_AWS_ACCESS_KEY_ID`     | `.env`          | Route53 DNS チャレンジ用 IAM キー                 | SSM から取得       |
| `PROXY_AWS_SECRET_ACCESS_KEY` | `.env`          | 同上シークレット                                  | SSM から取得       |
| `ROUTE53_HOSTED_ZONE_ID`      | `.env`          | Route53 ホストゾーン ID                           | SSM から取得       |

setup.sh を使う場合、SSM Parameter Store にアクセスできれば全て自動で埋まる。

### 4.5 HTTPS 設定（Route53 DNS チャレンジ）

Caddy が Route53 経由で Let's Encrypt 証明書を自動取得する。
ファイアウォールで 80/443 を IP 制限したままでも動作する。

Caddyfile をオーバーライドするため、サーバー上に配置：

```bash
cat > ~/plane/proxy-config/Caddyfile <<'EOF'
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
EOF
```

docker-compose.deploy.yml の proxy サービスに以下のボリュームマウントを追加：

```yaml
volumes:
  - caddy_data:/data
  - ./proxy-config/Caddyfile:/etc/caddy/Caddyfile:ro
```

#### IAM ユーザー

| ユーザー          | 用途                   | 権限                              |
| ----------------- | ---------------------- | --------------------------------- |
| `plane-caddy-dns` | Route53 DNS チャレンジ | 対象ゾーンの DNS レコード変更のみ |
| `plane-s3`        | ファイルストレージ     | 対象バケットの CRUD のみ          |

Route53 用ポリシー：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["route53:GetChange", "route53:ListHostedZonesByName"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["route53:ChangeResourceRecordSets", "route53:ListResourceRecordSets"],
      "Resource": "arn:aws:route53:::hostedzone/<HOSTED_ZONE_ID>"
    }
  ]
}
```

### 4.6 GHCR ログイン＆起動

```bash
echo "YOUR_GITHUB_PAT" | docker login ghcr.io -u <GITHUB_USER> --password-stdin
cd ~/plane
docker compose -f docker-compose.deploy.yml pull
docker compose -f docker-compose.deploy.yml up -d
```

初回起動はマイグレーション + collectstatic で **5〜10分** かかる（1GB インスタンスの場合）。

### 4.7 初期セットアップ

ブラウザでドメインにアクセスし、god-mode（Admin）で初期設定を行う。

初期設定完了後、Admin コンテナを停止してメモリを節約できる：

```bash
docker compose -f docker-compose.deploy.yml stop admin
```

再度 god-mode が必要な場合：

```bash
docker compose -f docker-compose.deploy.yml start admin
```

---

## アーキテクチャ

```
Internet
  │
  ├─ 80/443 (IP制限)
  │
  ▼
Caddy (proxy)  ─── HTTPS (Let's Encrypt via Route53 DNS challenge)
  │
  ├─ /api/*, /auth/*, /static/*  → API (gunicorn + embedded celery)
  ├─ /god-mode/*                 → Admin (nginx + Next.js)
  └─ /*                          → Web (nginx + Next.js)

API コンテナ (gunicorn worker + celery worker in same process)
    ──→ PostgreSQL
    ──→ Redis (キャッシュ + Celery ブローカー)
    ──→ S3 (ファイルストレージ、署名付き URL)
```

### コンテナ統合・削除の経緯

- **RabbitMQ → 削除**: Celery ブローカーを Redis に変更（`AMQP_URL=redis://plane-redis:6379/1`）
- **MinIO → 削除**: S3 に置き換え。署名付き URL でブラウザから直接アクセス
- **Worker → API プロセスに埋め込み**: gunicorn の `post_fork` フックで Celery worker をデーモンスレッドとして起動（`plane/gunicorn_conf.py`）。同一プロセスで Django のインポート済みモジュール（~120MB）を完全共有。`EMBED_CELERY=1` で有効化（デプロイ環境のみ）

### API + Worker を分離したい場合

`docker-compose.deploy.yml` で `EMBED_CELERY` を外し、別途 worker サービスを追加する。
Django のインポートが2重になるため、合計で ~120MB 多く消費する。

## メモリ構成（合計 ~428MB）

| サービス                | mem_limit | 実使用量 | 備考                                                 |
| ----------------------- | --------- | -------- | ---------------------------------------------------- |
| API (+ embedded Celery) | 256m      | ~194m    | gunicorn 1 worker + celery solo pool（同一プロセス） |
| Migrator                | 256m      | —        | 起動時のみ（完了後メモリ解放）                       |
| DB (PostgreSQL)         | 64m       | ~25m     | shared_buffers=32MB                                  |
| Web                     | 32m       | ~8m      | nginx 静的配信                                       |
| Admin                   | 32m       | ~7m      | 初期設定後は停止可                                   |
| Redis                   | 24m       | ~3m      | キャッシュ + Celery ブローカー                       |
| Proxy (Caddy)           | 16m       | ~11m     | HTTPS + リバースプロキシ                             |

---

## 運用

### 更新

```bash
cd ~/plane
docker compose -f docker-compose.deploy.yml pull
docker compose -f docker-compose.deploy.yml up -d
```

### ログ確認

```bash
docker compose -f docker-compose.deploy.yml logs -f          # 全体
docker compose -f docker-compose.deploy.yml logs api --tail 50 # API のみ
```

### ファイアウォールの IP 変更

```bash
MY_IP=$(curl -s ifconfig.io)
aws lightsail put-instance-public-ports --profile $PROFILE --region $REGION \
  --instance-name plane \
  --port-infos "[
    {\"fromPort\":22,\"toPort\":22,\"protocol\":\"tcp\",\"cidrs\":[\"${MY_IP}/32\"]},
    {\"fromPort\":80,\"toPort\":80,\"protocol\":\"tcp\",\"cidrs\":[\"${MY_IP}/32\"]},
    {\"fromPort\":443,\"toPort\":443,\"protocol\":\"tcp\",\"cidrs\":[\"${MY_IP}/32\"]}
  ]"
```

### メモリ確認

```bash
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}'
free -h
```

### 完全再作成

```bash
cd ~/plane
docker compose -f docker-compose.deploy.yml down
docker compose -f docker-compose.deploy.yml up -d
```

データは Docker ボリューム（`pgdata`, `redisdata`, `caddy_data`）に永続化されているため、コンテナ再作成でもデータは保持される。ファイルは S3 に保存。

---

## S3（ファイルストレージ）

| 項目               | 値                                                                                                        |
| ------------------ | --------------------------------------------------------------------------------------------------------- |
| バケット名         | SSM `/plane/s3-bucket-name`                                                                               |
| リージョン         | SSM `/plane/s3-region`                                                                                    |
| パブリックアクセス | **全ブロック**（BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets すべて true） |
| バケットポリシー   | なし                                                                                                      |
| アクセス方法       | Plane API が発行する署名付き URL（有効期限付き）のみ                                                      |
| IAM ユーザー       | `plane-s3`（バケット CRUD のみ、ListBuckets 不可）                                                        |

---

## DNS 設定（Route53）

ドメインの DNS を Route53 に移行済み。ネームサーバーは Value Domain から Route53 に切り替え済み。

Plane 用の A レコード：ドメイン → 静的 IP

---

## Docker イメージ（GHCR）

`keis` ブランチに push すると GitHub Actions で自動ビルドされ GHCR に公開される。
ドキュメントのみの変更（`*.md`, `docs/` 等）ではビルドがスキップされる。

| サービス | イメージ                                    |
| -------- | ------------------------------------------- |
| Web      | `ghcr.io/kamei-daisuke/plane-frontend:keis` |
| Admin    | `ghcr.io/kamei-daisuke/plane-admin:keis`    |
| API      | `ghcr.io/kamei-daisuke/plane-backend:keis`  |
| Proxy    | `ghcr.io/kamei-daisuke/plane-proxy:keis`    |
| Space    | `ghcr.io/kamei-daisuke/plane-space:keis`    |
| Live     | `ghcr.io/kamei-daisuke/plane-live:keis`     |

Proxy イメージは Go 1.25 + xcaddy でビルドし、以下のプラグインを含む：

- `caddy-dns/cloudflare`
- `caddy-dns/digitalocean`
- `caddy-dns/route53` (v1.6.0)

---

## シークレット管理（AWS SSM Parameter Store）

秘密情報は AWS SSM Parameter Store（SecureString）で管理。
setup.sh が自動で取得する。手動で確認/更新する場合：

```bash
# 一覧
aws ssm get-parameters-by-path --profile $PROFILE --region $REGION \
  --path /plane --with-decryption --query "Parameters[].{Name:Name,Value:Value}" --output table

# 個別取得
aws ssm get-parameter --profile $PROFILE --region $REGION \
  --name /plane/s3-access-key-id --with-decryption --query "Parameter.Value" --output text

# 更新
aws ssm put-parameter --profile $PROFILE --region $REGION \
  --name /plane/s3-access-key-id --type SecureString --value "NEW_VALUE" --overwrite
```

### パラメータ一覧

| パス                           | 型           | 用途                     |
| ------------------------------ | ------------ | ------------------------ |
| `/plane/s3-access-key-id`      | SecureString | S3 IAM アクセスキー      |
| `/plane/s3-secret-access-key`  | SecureString | S3 IAM シークレット      |
| `/plane/s3-bucket-name`        | String       | S3 バケット名            |
| `/plane/s3-region`             | String       | S3 リージョン            |
| `/plane/r53-access-key-id`     | SecureString | Route53 IAM アクセスキー |
| `/plane/r53-secret-access-key` | SecureString | Route53 IAM シークレット |
| `/plane/r53-hosted-zone-id`    | String       | Route53 ホストゾーン ID  |
| `/plane/site-domain`           | String       | ドメイン名               |
| `/plane/cert-email`            | String       | Let's Encrypt メール     |
| `/plane/ghcr-user`             | String       | GitHub ユーザー名        |

setup.sh は AWS CLI が利用可能な場合、SSM から自動取得する。
AWS CLI がない場合やアクセス権がない場合は対話式にフォールバックする。

---

## トラブルシューティング

### "Looks like Plane didn't start up correctly!"

API の起動を確認：

```bash
docker logs api 2>&1 | tail -20
```

よくある原因：

- `SECRET_KEY env variable is required.` → `apps/api/.env` に `SECRET_KEY` を追加
- `Waiting for database migrations to complete...` → migrator の完了を待つ（初回は5〜10分）
- OOM Killed → `docker inspect api --format '{{.State.OOMKilled}}'` で確認。メモリ不足なら mem_limit を上げる

### Proxy がリスタートを繰り返す

```bash
docker logs proxy 2>&1 | tail -10
```

- Caddyfile 関連のエラー → `./proxy-config/Caddyfile` が存在するか、ボリュームマウントが効いているか確認
- メモリ不足 → proxy の mem_limit を 32m 以上に

### HTTPS 証明書が取れない

```bash
docker logs proxy 2>&1 | grep "tls.obtain"
```

- `AccessDenied` → Route53 IAM 認証情報を確認（`PROXY_AWS_ACCESS_KEY_ID`, `PROXY_AWS_SECRET_ACCESS_KEY`）
- `Timeout during connect` → ファイアウォール問題。DNS チャレンジなら 80/443 の開放は不要
