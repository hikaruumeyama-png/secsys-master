import json
from typing import Any, Dict, Tuple

from flask import Request
from google.cloud import firestore

REGISTRY_COLLECTION = "agents_registry"


def _json_response(payload: Dict[str, Any], status: int = 200) -> Tuple[str, int, Dict[str, str]]:
    return json.dumps(payload, ensure_ascii=False), status, {"Content-Type": "application/json; charset=utf-8"}


def list_agents(request: Request):
    """HTTP Cloud Function: list available sub-agents from Firestore registry."""
    if request.method not in ("GET", "POST"):
        return _json_response({"error": "method not allowed"}, 405)

    status_filter = request.args.get("status")

    db = firestore.Client()
    query = db.collection(REGISTRY_COLLECTION)
    if status_filter:
        query = query.where("status", "==", status_filter)

    rows = []
    for doc in query.stream():
        item = doc.to_dict()
        created_at = item.get("created_at")
        if created_at is not None and hasattr(created_at, "isoformat"):
            item["created_at"] = created_at.isoformat()
        rows.append(item)

    rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return _json_response({"count": len(rows), "agents": rows})
