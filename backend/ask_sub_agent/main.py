import json
import os
from typing import Any, Dict, List, Tuple

from flask import Request
from google.cloud import discoveryengine_v1beta as discoveryengine


def _json_response(payload: Dict[str, Any], status: int = 200) -> Tuple[str, int, Dict[str, str]]:
    return json.dumps(payload, ensure_ascii=False), status, {"Content-Type": "application/json; charset=utf-8"}


def _build_serving_config(project_id: str, location: str, agent_id: str) -> str:
    return (
        f"projects/{project_id}/locations/{location}/collections/default_collection/"
        f"engines/{agent_id}/servingConfigs/default_search"
    )


def _extract_citations(results: List[discoveryengine.SearchResponse.SearchResult]) -> List[Dict[str, str]]:
    citations: List[Dict[str, str]] = []
    for r in results:
        doc = r.document
        link = doc.derived_struct_data.get("link") if doc.derived_struct_data else ""
        title = doc.derived_struct_data.get("title") if doc.derived_struct_data else ""
        citations.append({"title": str(title), "uri": str(link)})
    return citations


def ask_sub_agent(request: Request):
    """HTTP Cloud Function: query a specific Discovery Engine sub-agent and return answer candidates/citations."""
    if request.method != "POST":
        return _json_response({"error": "method not allowed"}, 405)

    data = request.get_json(silent=True) or {}
    agent_id = str(data.get("agent_id", "")).strip()
    question = str(data.get("question", "")).strip()

    if not agent_id or not question:
        return _json_response({"error": "agent_id and question are required"}, 400)

    project_id = os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GCP_LOCATION", "global")
    if not project_id:
        return _json_response({"error": "missing environment variable: GCP_PROJECT_ID"}, 500)

    client = discoveryengine.SearchServiceClient()
    serving_config = _build_serving_config(project_id, location, agent_id)
    request_obj = discoveryengine.SearchRequest(
        serving_config=serving_config,
        query=question,
        page_size=5,
    )
    response = client.search(request=request_obj)

    snippets = []
    for result in response.results:
        excerpt = ""
        if result.document and result.document.derived_struct_data:
            excerpt = str(result.document.derived_struct_data.get("snippet", ""))
        snippets.append(excerpt)

    return _json_response(
        {
            "agent_id": agent_id,
            "question": question,
            "answer_candidates": snippets,
            "citations": _extract_citations(list(response.results)),
        }
    )
