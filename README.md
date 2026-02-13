# SecSys-Master

セキュリティシステム課向け AI エージェント基盤です。

## アーキテクチャ

```text
┌─────────────┐     ┌──────────────────────┐     ┌──────────────┐
│ Google Chat  │────▶│ google_chat_handler   │────▶│ master_agent │
│（ユーザー）   │◀────│ (Webhook)             │◀────│ (ルーティング) │
└─────────────┘     └──────────────────────┘     └──────┬───────┘
                                                        │
                                    ┌───────────────────┼───────────────────┐
                                    ▼                   ▼                   ▼
                            ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
                            │ list_agents   │   │ask_sub_agent │   │ Sub-Agent N  │
                            │ (一覧取得)     │   │ (質問応答)    │   │ (Discovery   │
                            └──────────────┘   └──────────────┘   │  Engine)     │
                                                                  └──────────────┘

┌─────────────┐     ┌──────────────────────┐     ┌──────────────┐
│ 管理者       │────▶│ upload_document       │────▶│ create_agent │
│（PDF等upload）│◀────│ (工場機能)            │◀────│ (エージェント │
└─────────────┘     └──────────────────────┘     │  作成)       │
                            │                     └──────────────┘
                            ▼
                    ┌──────────────┐
                    │ Cloud Storage│
                    │ (ドキュメント) │
                    └──────────────┘
```

## 構成

```text
secsys-master/
├── cloudbuild.yaml
├── README.md
└── backend/
    ├── requirements_common.txt
    ├── create_agent/          # Phase 1: エージェント作成
    │   ├── main.py
    │   └── requirements.txt
    ├── list_agents/           # Phase 1: エージェント一覧
    │   ├── main.py
    │   └── requirements.txt
    ├── ask_sub_agent/         # Phase 1: サブエージェント問い合わせ
    │   ├── main.py
    │   └── requirements.txt
    ├── master_agent/          # Phase 2: ルーティングエージェント
    │   ├── main.py
    │   └── requirements.txt
    ├── google_chat_handler/   # Phase 2: Google Chat Webhook
    │   ├── main.py
    │   └── requirements.txt
    └── upload_document/       # Phase 2: ドキュメントアップロード工場
        ├── main.py
        └── requirements.txt
```

## Cloud Functions

### Phase 1（基盤API）

| 関数 | 説明 |
|------|------|
| `create_agent` | Agent Builder Search App を作成し、Firestore `agents_registry` に登録 |
| `list_agents` | Firestore の登録済みエージェントを一覧取得 |
| `ask_sub_agent` | 指定エージェントへ問い合わせし、回答候補と引用を返却 |

### Phase 2（統合プラットフォーム）

| 関数 | 説明 |
|------|------|
| `master_agent` | Vertex AI Gemini で質問を分析し、最適なサブエージェントに自動ルーティング |
| `google_chat_handler` | Google Chat Webhook を受信し、Master Agent と連携して Card v2 形式で回答 |
| `upload_document` | PDF 等をアップロードするだけで専用エージェントを自動作成する「工場」機能 |

## 必須環境変数

### create_agent
- `GCP_PROJECT_ID`
- `GCP_LOCATION` (例: `global`)

### list_agents
- なし（デフォルト認証で Firestore 接続）

### ask_sub_agent
- `GCP_PROJECT_ID`
- `GCP_LOCATION`

### master_agent
- `GCP_PROJECT_ID`
- `GCP_LOCATION` (例: `asia-northeast1`)
- `LIST_AGENTS_URL` — `list_agents` 関数の完全 URL
- `ASK_SUB_AGENT_URL` — `ask_sub_agent` 関数の完全 URL
- `AGENT_ENGINE_RESOURCE_NAME` (任意) — Agent Engine の resource name  
  例: `projects/<project>/locations/<region>/reasoningEngines/<id>`
- `AGENT_ENGINE_CLASS_METHOD` (任意) — `reasoningEngines.query` の `classMethod`（既定: `query`）
- `AGENT_ROUTING_MODE` (任意) — `agent_engine_primary` / `agent_engine_only` / `gemini`（既定: `agent_engine_primary`）
- `AGENT_ENGINE_FALLBACK_TO_GEMINI` (任意) — `true` の場合、Agent Engine失敗時にGeminiへフォールバック（既定: `false`）

### google_chat_handler
- `GCP_PROJECT_ID`
- `MASTER_AGENT_URL` — `master_agent` 関数の完全 URL

### upload_document
- `GCP_PROJECT_ID`
- `GCS_BUCKET_NAME` — ドキュメント保存先の GCS バケット名
- `CREATE_AGENT_URL` — `create_agent` 関数の完全 URL

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

### POST /master_agent
```json
{
  "question": "VPNがタイムアウトする時の確認項目は？"
}
```

レスポンス（エージェント一致時）:
```json
{
  "question": "VPNがタイムアウトする時の確認項目は？",
  "selected_agent": {
    "agent_id": "vpn-troubleshoot-bot-x9d",
    "display_name": "VPNトラブルシューティング担当",
    "reason": "VPN関連の質問のため"
  },
  "answer_candidates": ["..."],
  "citations": [{"title": "...", "uri": "..."}]
}
```

レスポンス（該当エージェントなし）:
```json
{
  "question": "今日の天気は？",
  "selected_agent": null,
  "message": "該当するエージェントが見つかりませんでした。",
  "reason": "天気に関するエージェントが登録されていません"
}
```

### POST /google_chat_handler
Google Chat Webhook から自動呼び出し。Card v2 形式のレスポンスを返却。

### POST /upload_document (multipart/form-data)
```
file: (バイナリ: PDF, TXT, HTML, CSV)
display_name: "VPNマニュアル担当"
description: "VPN接続に関する問い合わせ対応"
```

レスポンス:
```json
{
  "ok": true,
  "agent": {
    "agent_id": "agent-1707568800",
    "display_name": "VPNマニュアル担当",
    "description": "VPN接続に関する問い合わせ対応",
    "gcs_source": "gs://bucket/agent-1707568800/vpn_manual.pdf"
  },
  "message": "エージェントを作成しました。インデックス構築には数分かかる場合があります。"
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

Master 側が呼ぶ関数のみ実行可能にします。

```bash
for fn in create_agent list_agents ask_sub_agent upload_document master_agent google_chat_handler; do
  gcloud functions add-invoker-policy-binding "$fn" \
    --gen2 \
    --region=asia-northeast1 \
    --member="serviceAccount:sa-secsys-master@${PROJECT_ID}.iam.gserviceaccount.com"
done
```

### 4) Cloud Functions は Worker SA を明示

本リポジトリの `cloudbuild.yaml` では、Cloud Functions (Gen2) のデプロイ時に
`--service-account=sa-secsys-worker@${PROJECT_ID}.iam.gserviceaccount.com` を指定します。

手動デプロイ時も同様に `--service-account` を必ず付与してください。

### 5) Agent 設定（Master 実行主体）

Master Agent 側では次を設定します。

- 実行 SA: `sa-secsys-master@${PROJECT_ID}.iam.gserviceaccount.com`
- 認証方式: ID トークン付きで各 HTTPS Endpoint を呼び出す
- 必要最小権限は `sa-secsys-worker` と `sa-secsys-master` のみに付与する
- default SA（Compute/App Engine）には新規ロールを付与しない

## 認証付きHTTP呼び出しテスト（Master SA）

全関数について「未認証は拒否、`sa-secsys-master` のみ許可」を検証します。

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

## Google Chat Bot 設定

1. [Google Cloud Console](https://console.cloud.google.com/) で Google Chat API を有効化
2. Chat API 設定で以下を構成:
   - **Bot name**: セキュリティシステム課 AI
   - **Avatar URL**: (任意)
   - **Connection settings**: HTTP endpoint URL → `google_chat_handler` 関数の URL
   - **Permissions**: 組織内の特定ユーザー/グループ
   - **動作仕様**:
     - 個別チャット（DM）: ユーザーのメッセージに常時応答
     - スペース: Bot がメンションされたメッセージのみに応答

## 初期セットアップ手順（本番運用向け）

以下を **default compute SA / appspot SA / 個人 Owner・Editor に依存しない** 前提で実施します。

1. SA 作成

```bash
gcloud iam service-accounts create sa-secsys-worker \
  --display-name="SecSys Worker Runtime"

gcloud iam service-accounts create sa-secsys-master \
  --display-name="SecSys Master Agent Runtime"
```

2. Worker SA に実行権限を付与

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

3. Master SA に関数呼び出し権限を付与

```bash
for fn in create_agent list_agents ask_sub_agent upload_document master_agent google_chat_handler; do
  gcloud functions add-invoker-policy-binding "$fn" \
    --gen2 \
    --region=asia-northeast1 \
    --member="serviceAccount:sa-secsys-master@${PROJECT_ID}.iam.gserviceaccount.com"
done
```

4. GCS バケット作成（ドキュメントアップロード用）

```bash
gsutil mb -l asia-northeast1 gs://${PROJECT_ID}-secsys-docs
```

5. 検証スクリプトを実行（未認証は 401/403、master SA は 200系を確認）

```bash
PROJECT_ID=${PROJECT_ID} \
MASTER_SA=sa-secsys-master@${PROJECT_ID}.iam.gserviceaccount.com \
bash scripts/test_master_sa_invoker.sh
```

6. Cloud Build 実行 SA の最終確認

```bash
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)')
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
WORKER_SA="sa-secsys-worker@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts get-iam-policy "$WORKER_SA" \
  --format="json(bindings)" \
  --flatten="bindings[]" \
  --filter="bindings.members:serviceAccount:${CB_SA} AND bindings.role:roles/iam.serviceAccountUser"

gcloud projects get-iam-policy ${PROJECT_ID} \
  --flatten="bindings[]" \
  --filter="bindings.members:serviceAccount:${CB_SA}" \
  --format="table(bindings.role)"
```

7. default SA / appspot SA / 個人 Owner・Editor 依存の排除確認

```bash
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)')
DEFAULT_COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
APPSPOT_SA="${PROJECT_ID}@appspot.gserviceaccount.com"

gcloud projects get-iam-policy ${PROJECT_ID} \
  --flatten="bindings[]" \
  --filter="bindings.members:serviceAccount:${DEFAULT_COMPUTE_SA} OR bindings.members:serviceAccount:${APPSPOT_SA}" \
  --format="table(bindings.role, bindings.members)"

gcloud projects get-iam-policy ${PROJECT_ID} \
  --flatten="bindings[]" \
  --filter="(bindings.role=roles/owner OR bindings.role=roles/editor) AND bindings.members:user:*" \
  --format="table(bindings.role, bindings.members)"
```
