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

## IAM 設計（default SA / Owner-Editor 非依存）

default の Compute Engine SA / App Engine SA や、人ユーザーへの Owner・Editor 付与を前提にせず、用途別 SA に最小権限のみ付与します。

### 1) 専用 SA の作成

```bash
gcloud iam service-accounts create sa-secsys-worker \
  --display-name="SecSys Worker Runtime"

gcloud iam service-accounts create sa-secsys-master \
  --display-name="SecSys Master Agent Runtime"
```

### 2) `sa-secsys-worker` に実行時ロールを付与

以下をプロジェクトに付与します。

```bash
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:sa-secsys-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/discoveryengine.admin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:sa-secsys-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:sa-secsys-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:sa-secsys-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:sa-secsys-worker@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```

### 3) `sa-secsys-master` にはサブエージェント呼び出し権限のみ付与

Master 側が呼ぶ `list_agents` / `ask_sub_agent` のみ実行可能にします（`create_agent` は付与しない）。

```bash
gcloud functions add-invoker-policy-binding list_agents \
  --region=asia-northeast1 \
  --member="serviceAccount:sa-secsys-master@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud functions add-invoker-policy-binding ask_sub_agent \
  --region=asia-northeast1 \
  --member="serviceAccount:sa-secsys-master@${PROJECT_ID}.iam.gserviceaccount.com"
```

### 4) Cloud Functions は Worker SA を明示

本リポジトリの `cloudbuild.yaml` では、Cloud Functions (Gen2) のデプロイ時に
`--service-account=sa-secsys-worker@${PROJECT_ID}.iam.gserviceaccount.com` を指定します。

手動デプロイ時も同様に `--service-account` を必ず付与してください。

### 5) Agent 設定（Master 実行主体）

Master Agent 側では次を設定します。

- 実行 SA: `sa-secsys-master@${PROJECT_ID}.iam.gserviceaccount.com`
- 認証方式: ID トークン付きで `list_agents` と `ask_sub_agent` の HTTPS Endpoint を呼び出す
- 呼び出し対象: 運用上必要な Sub-agent API のみ（`create_agent` を通常経路から除外）

- 必要最小権限は `sa-secsys-worker` と `sa-secsys-master` のみに付与する
- default SA（Compute/App Engine）には新規ロールを付与しない

## 認証付きHTTP呼び出しテスト（Master SA）

`create_agent` / `list_agents` / `ask_sub_agent` について、
「未認証は拒否、`sa-secsys-master` のみ許可」を検証するためのスクリプトを追加しています。

```bash
PROJECT_ID=<your-project-id> \
MASTER_SA=sa-secsys-master@<your-project-id>.iam.gserviceaccount.com \
bash scripts/test_master_sa_invoker.sh
```

動作:
- 未認証で各関数URLへ HTTP 呼び出し（401/403 を期待）
- `sa-secsys-master` を impersonate して ID トークン付きで呼び出し
- 認証付き呼び出しが 403 の場合、対象 Gen2 関数の Cloud Run サービスへ
  `roles/run.invoker` を `sa-secsys-master` に付与して再試行

> 実行には `gcloud` CLI と、`functions.describe` / `run.services.getIamPolicy` /
> `run.services.setIamPolicy` / `iam.serviceAccounts.getOpenIdToken` 相当の権限が必要です。
これにより、SecSys の実行経路は default SA や人ユーザー Owner/Editor 権限に依存しません。
