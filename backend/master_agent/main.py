import json
import os
import re
from typing import Any, Dict, Tuple

import requests as http_requests
from flask import Request

import google.auth.transport.requests
import google.oauth2.id_token
import vertexai
from vertexai.generative_models import GenerativeModel


def _json_response(payload: Dict[str, Any], status: int = 200) -> Tuple[str, int, Dict[str, str]]:
    return json.dumps(payload, ensure_ascii=False), status, {"Content-Type": "application/json; charset=utf-8"}


def _required(data: Dict[str, Any], field: str) -> str:
    value = str(data.get(field, "")).strip()
    if not value:
        raise ValueError(f"missing required field: {field}")
    return value


def _get_id_token(target_url: str) -> str:
    auth_req = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(auth_req, target_url)


def _fetch_agents(list_agents_url: str) -> list:
    token = _get_id_token(list_agents_url)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = http_requests.get(list_agents_url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get("agents", [])


def _build_routing_prompt(agents: list, question: str) -> str:
    agent_descriptions = []
    for a in agents:
        agent_descriptions.append(
            f"- agent_id: {a.get('agent_id')}, "
            f"display_name: {a.get('display_name')}, "
            f"description: {a.get('description')}"
        )
    agents_text = "\n".join(agent_descriptions)

    return (
        "あなたはルーティングAIです。以下のエージェント一覧とユーザーの質問を見て、"
        "最も適切なエージェントを1つ選んでください。\n\n"
        f"## エージェント一覧\n{agents_text}\n\n"
        f"## ユーザーの質問\n{question}\n\n"
        "## 出力形式\n"
        "以下のJSON形式のみを出力してください。それ以外のテキストは含めないでください。\n"
        '該当するエージェントがある場合: {"agent_id": "selected-id", "reason": "選択理由"}\n'
        '該当するエージェントがない場合: {"agent_id": null, "reason": "該当しない理由"}\n'
    )


def _parse_gemini_json(text: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Gemini response did not contain valid JSON")
    return json.loads(match.group())


def master_agent(request: Request):
    """HTTP Cloud Function: route user questions to the best sub-agent via Gemini."""
    if request.method != "POST":
        return _json_response({"error": "method not allowed"}, 405)

    try:
        data = request.get_json(silent=True) or {}
        question = _required(data, "question")

        project_id = os.environ["GCP_PROJECT_ID"]
        location = os.environ.get("GCP_LOCATION", "asia-northeast1")
        list_agents_url = os.environ["LIST_AGENTS_URL"]
        ask_sub_agent_url = os.environ["ASK_SUB_AGENT_URL"]

        # 1) Fetch available agents
        agents = _fetch_agents(list_agents_url)

        if not agents:
            return _json_response({
                "question": question,
                "selected_agent": None,
                "message": "該当するエージェントが見つかりませんでした。",
                "reason": "登録されているエージェントがありません。",
            })

        # 2) Ask Gemini to pick the best agent
        prompt = _build_routing_prompt(agents, question)
        vertexai.init(project=project_id, location=location)
        model = GenerativeModel("gemini-2.0-flash")
        gemini_response = model.generate_content(prompt)
        selection = _parse_gemini_json(gemini_response.text)

        selected_agent_id = selection.get("agent_id")
        reason = selection.get("reason", "")

        # 3) If no agent matched, return early
        if not selected_agent_id:
            return _json_response({
                "question": question,
                "selected_agent": None,
                "message": "該当するエージェントが見つかりませんでした。",
                "reason": reason,
            })

        # 4) Find display_name from agent list
        display_name = ""
        for a in agents:
            if a.get("agent_id") == selected_agent_id:
                display_name = a.get("display_name", "")
                break

        # 5) Call the selected sub-agent
        token = _get_id_token(ask_sub_agent_url)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        sub_resp = http_requests.post(
            ask_sub_agent_url,
            headers=headers,
            json={"agent_id": selected_agent_id, "question": question},
            timeout=60,
        )
        sub_resp.raise_for_status()
        sub_data = sub_resp.json()

        return _json_response({
            "question": question,
            "selected_agent": {
                "agent_id": selected_agent_id,
                "display_name": display_name,
                "reason": reason,
            },
            "answer_candidates": sub_data.get("answer_candidates", []),
            "citations": sub_data.get("citations", []),
        })

    except KeyError as e:
        return _json_response({"error": f"missing environment variable: {e.args[0]}"}, 500)
    except ValueError as e:
        return _json_response({"error": str(e)}, 400)
    except http_requests.RequestException as e:
        return _json_response({"error": "upstream service error", "detail": str(e)}, 502)
    except Exception as e:  # noqa: BLE001
        return _json_response({"error": "internal server error", "detail": str(e)}, 500)
