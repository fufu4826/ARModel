"""Infrastructure helpers for the GitHub Contents API."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen


JsonRequester = Callable[[str, str, dict | None], dict]


def request_json(
    method: str,
    api_path: str,
    token: str,
    payload: dict | None = None,
    *,
    opener=urlopen,
    timeout: int = 45,
) -> dict:
    """Send an authenticated GitHub API request and decode its JSON response."""
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_obj = Request(
        f"https://api.github.com{api_path}",
        data=data,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ARModel-Production-Admin/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method=method,
    )
    with opener(request_obj, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def commit_json(
    relative_path: str,
    value,
    *,
    repository: str,
    branch: str,
    requester: JsonRequester,
    committer_name: str = "",
    committer_email: str = "",
) -> None:
    """Commit a JSON value through an injected GitHub Contents requester."""
    content_api_path = f"/repos/{repository}/contents/{quote(relative_path, safe='/')}"
    current = requester("GET", f"{content_api_path}?ref={quote(branch, safe='')}", None)
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    payload = {
        "message": f"Update {relative_path} from production admin",
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
        "sha": current.get("sha"),
    }
    if committer_name and committer_email:
        payload["committer"] = {"name": committer_name, "email": committer_email}
    requester("PUT", content_api_path, payload)
