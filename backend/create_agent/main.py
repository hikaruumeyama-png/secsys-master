import datetime
import json
import os
from typing import Any, Dict, Tuple

from flask import Request
from google.api_core.exceptions import GoogleAPIError
from google.cloud import discoveryengine_v1beta as discoveryengine
from google.cloud import firestore

REGISTRY_COLLECTION = "agents_registry"


def _json_response(payload: Dict[str, Any], status: int = 200) -> Tuple[str, int, Dict[str, str]]:
    return json.dumps(payload, ensure_ascii=False), status, {"Content-Type": "application/json; charset=utf-8"}


def _required(data: Dict[str, Any], field: str) -> str:
    value = str(data.get(field, "")).strip()
    if not value:
        raise ValueError(f"missing required field: {field}")
    return value


def create_agent(request: Request):
    """HTTP Cloud Function: create Discovery Engine Search app and register metadata in Firestore."""
    if request.method != "POST":
        return _json_response({"error": "method not allowed"}, 405)

    try:
        data = request.get_json(silent=True) or {}
        display_name = _required(data, "display_name")
        description = _required(data, "description")
        gcs_source = _required(data, "gcs_source")

        project_id = os.environ["GCP_PROJECT_ID"]
        location = os.environ.get("GCP_LOCATION", "global")

        engine_id = data.get("agent_id") or f"agent-{int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())}"

        # 1) Create Engine (search app)
        engine_client = discoveryengine.EngineServiceClient()
        parent = f"projects/{project_id}/locations/{location}/collections/default_collection"
        engine = discoveryengine.Engine(
            display_name=display_name,
            solution_type=discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH,
        )
        operation = engine_client.create_engine(parent=parent, engine=engine, engine_id=engine_id)
        operation.result(timeout=600)

        # 2) Register in Firestore
        db = firestore.Client(project=project_id)
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        doc = {
            "agent_id": engine_id,
            "display_name": display_name,
            "description": description,
            "gcs_source": gcs_source,
            "created_at": now,
            "status": "active",
        }
        db.collection(REGISTRY_COLLECTION).document(engine_id).set(doc)

        return _json_response({"ok": True, "agent": doc}, 201)

    except KeyError as e:
        return _json_response({"error": f"missing environment variable: {e.args[0]}"}, 500)
    except ValueError as e:
        return _json_response({"error": str(e)}, 400)
    except GoogleAPIError as e:
        return _json_response({"error": "google api error", "detail": str(e)}, 502)
    except Exception as e:  # noqa: BLE001
        return _json_response({"error": "internal server error", "detail": str(e)}, 500)
