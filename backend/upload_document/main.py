import datetime
import json
import os
import pathlib
from typing import Any, Dict, Tuple

import google.auth.transport.requests
import google.oauth2.id_token
import requests
from flask import Request
from google.api_core.exceptions import GoogleAPIError
from google.cloud import storage

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".html", ".csv"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".html": "text/html",
    ".csv": "text/csv",
}


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


def _upload_to_gcs(bucket_name: str, blob_path: str, file_data: bytes, content_type: str) -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(file_data, content_type=content_type)
    return f"gs://{bucket_name}/{blob_path}"


def upload_document(request: Request):
    """HTTP Cloud Function: upload a document and create a Discovery Engine agent."""
    if request.method != "POST":
        return _json_response({"error": "method not allowed"}, 405)

    try:
        # Parse multipart form data
        file = request.files.get("file")
        if not file or not file.filename:
            raise ValueError("file is required")

        display_name = (request.form.get("display_name") or "").strip()
        if not display_name:
            raise ValueError("missing required field: display_name")

        description = (request.form.get("description") or "").strip()
        if not description:
            raise ValueError("missing required field: description")

        # Validate file extension
        ext = pathlib.PurePosixPath(file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"unsupported file type: {ext} (allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))})")

        # Validate file size
        file_data = file.read()
        if len(file_data) > MAX_FILE_SIZE:
            raise ValueError(f"file too large: {len(file_data)} bytes (max {MAX_FILE_SIZE} bytes)")

        # Environment variables
        bucket_name = os.environ["GCS_BUCKET_NAME"]
        create_agent_url = os.environ["CREATE_AGENT_URL"]

        # Generate agent ID
        agent_id = f"agent-{int(datetime.datetime.now(tz=datetime.timezone.utc).timestamp())}"

        # Upload to GCS
        blob_path = f"{agent_id}/{file.filename}"
        content_type = CONTENT_TYPES.get(ext, "application/octet-stream")
        gcs_uri = _upload_to_gcs(bucket_name, blob_path, file_data, content_type)

        # Call create_agent endpoint
        id_token = _get_id_token(create_agent_url)
        resp = requests.post(
            create_agent_url,
            json={
                "display_name": display_name,
                "description": description,
                "gcs_source": gcs_uri,
                "agent_id": agent_id,
            },
            headers={"Authorization": f"Bearer {id_token}"},
            timeout=660,
        )
        resp.raise_for_status()

        return _json_response(
            {
                "ok": True,
                "agent": {
                    "agent_id": agent_id,
                    "display_name": display_name,
                    "description": description,
                    "gcs_source": gcs_uri,
                },
                "message": "エージェントを作成しました。インデックス構築には数分かかる場合があります。",
            },
            201,
        )

    except KeyError as e:
        return _json_response({"error": f"missing environment variable: {e.args[0]}"}, 500)
    except ValueError as e:
        return _json_response({"error": str(e)}, 400)
    except (requests.RequestException, GoogleAPIError) as e:
        return _json_response({"error": "upstream service error", "detail": str(e)}, 502)
    except Exception as e:  # noqa: BLE001
        return _json_response({"error": "internal server error", "detail": str(e)}, 500)
