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
