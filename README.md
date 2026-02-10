# SecSys-Master

セキュリティシステム課向け AI エージェント基盤（Phase 1）実装です。

## 構成

```text
secsys-master/
├── cloudbuild.yaml
├── README.md
└── backend/
    ├── requirements_common.txt
    ├── create_agent/
    │   ├── main.py
    │   └── requirements.txt
    ├── list_agents/
    │   ├── main.py
    │   └── requirements.txt
    └── ask_sub_agent/
        ├── main.py
        └── requirements.txt
```

## Cloud Functions

- `create_agent`: Agent Builder Search App を作成し、Firestore `agents_registry` に登録
- `list_agents`: Firestore の登録済みエージェントを一覧取得
- `ask_sub_agent`: 指定エージェントへ問い合わせし、回答候補と引用を返却

## 必須環境変数

### create_agent
- `GCP_PROJECT_ID`
- `GCP_LOCATION` (例: `global`)
- `DATA_STORE_LOCATION` (例: `global`)

### list_agents
- なし（デフォルト認証で Firestore 接続）

### ask_sub_agent
- `GCP_PROJECT_ID`
- `GCP_LOCATION`

## API I/O（概要）

### POST /create_agent
```json
{
  "display_name": "VPNトラブルシューティング担当",
  "description": "VPN接続エラーを回答",
  "gcs_source": "gs://secsys-docs/vpn_manual.pdf"
}
```

### GET /list_agents
- クエリ: `status`（任意）

### POST /ask_sub_agent
```json
{
  "agent_id": "vpn-troubleshoot-bot-x9d",
  "question": "VPNがタイムアウトする時の確認項目は？"
}
```

## デプロイ

Cloud Build Trigger で `cloudbuild.yaml` を実行してください。

```bash
git push origin main
```

## サービスアカウント運用（default SA 非依存）

default の Compute Engine / App Engine サービスアカウントに権限を足す運用は行わず、用途別 SA を明示的に使用します。

### 1) 専用 SA の作成

```bash
gcloud iam service-accounts create sa-secsys-worker \
  --display-name="SecSys Worker Runtime"

gcloud iam service-accounts create sa-secsys-master \
  --display-name="SecSys Master Agent Runtime"
```

### 2) Cloud Functions は Worker SA を明示

本リポジトリの `cloudbuild.yaml` では、Cloud Functions (Gen2) のデプロイ時に
`--service-account=sa-secsys-worker@${PROJECT_ID}.iam.gserviceaccount.com` を指定済みです。

手動デプロイ時も同様に `--service-account` を必ず付与してください。

### 3) Master Agent は Master SA を実行主体に設定

Master Agent 側の実行主体は以下を設定してください。

- `sa-secsys-master@${PROJECT_ID}.iam.gserviceaccount.com`

### 4) IAM 付与方針

- 必要最小権限は `sa-secsys-worker` と `sa-secsys-master` のみに付与する
- default SA（Compute/App Engine）には新規ロールを付与しない
