import json
import logging
import os
from typing import Any, Dict, Tuple

import google.auth.transport.requests
import google.oauth2.id_token
import requests
from flask import Request

logger = logging.getLogger(__name__)

MASTER_AGENT_URL = os.environ.get("MASTER_AGENT_URL", "")


def _json_response(payload: Dict[str, Any], status: int = 200) -> Tuple[str, int, Dict[str, str]]:
    return json.dumps(payload, ensure_ascii=False), status, {"Content-Type": "application/json; charset=utf-8"}


def _get_id_token(target_url: str) -> str:
    auth_req = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(auth_req, target_url)


def _build_card_response(master_response: dict) -> dict:
    selected = master_response.get("selected_agent")

    if selected is None:
        return {
            "text": master_response.get("message", "該当するエージェントが見つかりませんでした。")
        }

    agent_name = selected.get("display_name", selected.get("agent_id", "不明"))
    answer_candidates = master_response.get("answer_candidates", [])
    citations = master_response.get("citations", [])

    answer_text = "\n\n".join(c for c in answer_candidates if c) or "回答が見つかりませんでした。"

    sections = [
        {
            "header": "回答",
            "widgets": [{"textParagraph": {"text": answer_text}}]
        }
    ]

    if citations:
        citation_widgets = []
        for c in citations[:5]:
            title = c.get("title", "参照元")
            uri = c.get("uri", "")
            if uri:
                citation_widgets.append({
                    "decoratedText": {
                        "text": title,
                        "button": {
                            "text": "開く",
                            "onClick": {"openLink": {"url": uri}}
                        }
                    }
                })
        if citation_widgets:
            sections.append({
                "header": "参照元",
                "widgets": citation_widgets
            })

    return {
        "cardsV2": [{
            "cardId": "agent-response",
            "card": {
                "header": {
                    "title": f"\U0001f916 {agent_name}",
                    "subtitle": selected.get("reason", "")
                },
                "sections": sections
            }
        }]
    }


def _call_master_agent(text: str) -> dict:
    token = _get_id_token(MASTER_AGENT_URL)
    resp = requests.post(
        MASTER_AGENT_URL,
        json={"question": text},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def google_chat_handler(request: Request):
    """HTTP Cloud Function: Google Chat webhook handler."""
    try:
        event = request.get_json(silent=True) or {}
        event_type = event.get("type", "")

        if event_type == "ADDED_TO_SPACE":
            return {
                "text": "セキュリティシステム課 AIアシスタントです。\n"
                        "質問を入力してください。登録済みの専門エージェントが自動で回答します。"
            }

        if event_type == "REMOVED_FROM_SPACE":
            return {}

        if event_type == "MESSAGE":
            message = event.get("message", {})
            text = (message.get("argumentText") or message.get("text") or "").strip()

            if not text:
                return {"text": "テキストを入力してください。"}

            if not MASTER_AGENT_URL:
                logger.error("MASTER_AGENT_URL is not configured")
                return {"text": "エラー: MASTER_AGENT_URL が設定されていません。"}

            try:
                master_response = _call_master_agent(text)
            except Exception as exc:
                logger.exception("master_agent call failed")
                return {"text": f"エラーが発生しました: {exc}"}

            return _build_card_response(master_response)

        return {}

    except Exception as exc:
        logger.exception("google_chat_handler unexpected error")
        return {"text": f"予期しないエラーが発生しました: {exc}"}
