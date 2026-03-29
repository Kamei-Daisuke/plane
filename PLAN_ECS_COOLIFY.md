# Coolify + Spot 構築計画

## Context

現在 4 つのサービスが個別の EC2/Lightsail で動いており月額 $31。
Spot (r6g.medium) 1 台に Coolify をインストールし、全サービスを統合する。
Coolify の Web UI で Git push 自動デプロイ、HTTPS 自動、DB ワンクリック管理。

## 対象サービス

| サービス | 現在の場所 | 月額 | フレームワーク |
|---|---|---|---|
| Plane | Lightsail | $7 | Django + Next.js + PostgreSQL + Redis |
| YMCA | EC2 t3.micro | $8 | Java Spring Boot (GraalVM 予定) |
| Crane | EC2 t3.micro | $8 | Django + PostgreSQL |
| Keis WordPress | EC2 t3.micro | $8 | WordPress + PHP + MariaDB |
| **合計** | | **$31** | |

## アーキテクチャ

```
Internet
  │
  ├── DNS (Route53) → EC2 パブリック IP（User Data で自動更新）
  │
  ▼
Coolify (Traefik 内蔵 → 自動 HTTPS)
  ├── example.com          → WordPress
  ├── plane.example.com    → Plane
  ├── ymca.example.com     → YMCA
  └── crane.example.com    → Crane

Spot r6g.medium (1vCPU / 8GB RAM)
  ├── Coolify 本体 (~500MB)
  ├── Traefik (リバースプロキシ + TLS)
  ├── Plane (API+Celery+Web+Admin+PostgreSQL+Redis)
  ├── YMCA (GraalVM native image)
  ├── Crane (Django + PostgreSQL 共用)
  └── WordPress (PHP-FPM + MariaDB)

EBS ボリューム (AZ 固定: ap-northeast-1c)
  └── ebs-coolify (50GB gp3) → /data
      ├── /data/coolify (Coolify 設定・DB)
      ├── /data/postgres (PostgreSQL)
      ├── /data/redis (Redis)
      ├── /data/wordpress (WordPress files + MariaDB)
      └── /data/docker (Docker volumes)
```

## ECS との比較

| 項目 | ECS | Coolify |
|---|---|---|
| デプロイ | CLI + JSON | Web UI + Git push |
| HTTPS | Caddy 自前構築 | 自動（Traefik） |
| DB 管理 | 手動構築 | ワンクリック |
| サービス追加 | タスク定義作成 | Web UI でポチ |
| 死活監視 | ECS サービス | Docker restart policy |
| Spot 復旧 | ASG + User Data | ASG + User Data（同じ） |
| 学習コスト | 高い | 低い |

## 実装フェーズ

### Phase 1: インフラ基盤
1. VPC 作成 (10.50.0.0/16) ← 済み
2. セキュリティグループ (80, 443, 22, 8000[Coolify UI] from マイ IP)
3. EBS ボリューム 1 本 (50GB gp3, ap-northeast-1c)
4. IAM ロール (EC2 用: EBS アタッチ + Route53 更新 + SSM 読み取り)

### Phase 2: Spot + Coolify セットアップ
5. Launch Template 作成
   - AMI: Ubuntu 22.04 ARM64
   - User Data:
     - EBS アタッチ + マウント (/data)
     - Route53 に自分の IP を登録
     - Coolify インストール（/data にデータ保存）
     - Docker 自動起動
6. Auto Scaling Group (Spot, min=0, max=1, desired=1, AZ=ap-northeast-1c)

### Phase 3: Coolify でサービスデプロイ
7. Coolify Web UI にアクセス、初期設定
8. Plane デプロイ
   - docker-compose.deploy.yml をベースに Coolify で管理
   - PostgreSQL + Redis を Coolify の DB 機能で作成
   - 環境変数は SSM から取得したものを設定
9. WordPress デプロイ
   - Coolify の WordPress テンプレートを使用
   - MariaDB を Coolify で作成
   - 既存データを移行
10. YMCA デプロイ
    - GitHub リポから自動ビルド（ARM native image）
    - Coolify の Docker 設定で管理
11. Crane デプロイ
    - GitHub リポから自動ビルド
    - PostgreSQL は Plane と共用（別 DB 名）

### Phase 4: DNS 切り替え
12. Route53 レコード更新
    - example.com → 新 IP
    - plane.example.com → 新 IP
    - ymca.example.com → 新 IP（新規追加）
    - crane.example.com → 新 IP
13. 各サービスの HTTPS + 動作確認

### Phase 5: 移行 + 旧インフラ停止
14. 動作確認（全サービス）
15. 旧 EC2 停止 (ymca-prod, crane-prd, new-keis-wordpress-02)
16. Lightsail 停止 (plane)
17. 不要な VPC / セキュリティグループ / EBS の整理

## Spot 中断時の復旧フロー

```
Spot 中断通知 (2分前)
  │
  ▼
インスタンス終了
  │
  ▼
ASG が新インスタンス起動 (同 AZ: ap-northeast-1c)
  │
  ▼
User Data 実行:
  1. EBS (ebs-coolify) をアタッチ → /data にマウント
  2. 自分のパブリック IP を取得
  3. Route53 の A レコードを全ドメイン更新
  4. Coolify 起動 (/data/coolify から設定読み込み)
  5. Docker Compose で全サービス自動起動
  │
  ▼
復旧完了 (推定 2-5 分)
```

## メモリバジェット (r6g.medium = 8GB)

| 項目 | メモリ目安 |
|---|---|
| OS + Docker | ~300MB |
| Coolify + Traefik | ~500MB |
| Plane (API+Celery+Web+Admin) | ~500MB |
| Plane (PostgreSQL + Redis) | ~200MB |
| YMCA (GraalVM native) | ~100MB |
| Crane (Django) | ~200MB |
| WordPress (PHP-FPM + MariaDB) | ~400MB |
| **合計** | **~2,200MB** |
| **バッファ** | **~5,800MB** |

## コスト見積もり

| 項目 | 月額 |
|---|---|
| r6g.medium Spot | ~$7-9 |
| EBS 50GB gp3 | ~$4.8 |
| S3 (plane-keis-uploads) | ~$1 |
| Route53 | $0.50 |
| データ転送 | ~$1-3 |
| **合計** | **~$14-18** |
| **現状** | **$31** |
| **削減** | **42-55%** |

## リスクと対策

| リスク | 対策 |
|---|---|
| Spot 中断 | ASG 自動復旧 + EBS 再アタッチ + Route53 自動更新 |
| Coolify 自体の障害 | Docker restart policy + EBS にデータ永続化 |
| メモリ不足 | 8GB 中 ~2.2GB 使用、5.8GB バッファ。十分余裕 |
| DB データロスト | EBS で永続化。Spot 中断でも EBS は残る |
| EBS アタッチ失敗 | User Data にリトライロジック |

## 検証方法

1. Coolify Web UI にアクセスできること
2. 各ドメインに HTTPS でアクセスできること
3. Plane: ログイン → ワークスペース操作
4. YMCA: 正常動作
5. Crane: 正常動作
6. WordPress: 管理画面 + フロント表示
7. Spot 中断シミュレーション: インスタンス terminate → 自動復旧確認
