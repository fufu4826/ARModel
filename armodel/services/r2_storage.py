"""Cloudflare R2 infrastructure primitives using the S3-compatible API."""

from __future__ import annotations

import hashlib
import hmac
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen


SignedRequester = Callable[..., object]


def signed_request(
    method: str,
    object_key: str,
    payload_hash: str,
    *,
    account_id: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    extra_headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: int = 120,
    query_params: dict[str, str] | None = None,
    now: datetime | None = None,
    opener=urlopen,
):
    """Create and execute an AWS Signature V4 request against R2."""
    host = f"{account_id}.r2.cloudflarestorage.com"
    canonical_uri = f"/{quote(bucket, safe='')}"
    if object_key:
        canonical_uri += f"/{quote(object_key, safe='/-_.~')}"
    canonical_query = ""
    if query_params:
        canonical_query = "&".join(
            f"{quote(str(key), safe='-_.~')}={quote(str(value), safe='-_.~')}"
            for key, value in sorted(query_params.items())
        )
    endpoint = f"https://{host}{canonical_uri}"
    if canonical_query:
        endpoint += f"?{canonical_query}"

    timestamp = now or datetime.now(timezone.utc)
    amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = timestamp.strftime("%Y%m%d")
    headers = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if extra_headers:
        headers.update({key.lower(): value for key, value in extra_headers.items()})
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
    canonical_request = "\n".join(
        [method, canonical_uri, canonical_query, canonical_headers, signed_headers, payload_hash]
    )
    credential_scope = f"{date_stamp}/auto/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    def sign(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()

    signing_key = sign(
        sign(sign(sign(("AWS4" + secret_key).encode("utf-8"), date_stamp), "auto"), "s3"),
        "aws4_request",
    )
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    auth_header = (
        "AWS4-HMAC-SHA256 "
        f"Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    request_headers = dict(extra_headers or {})
    request_headers.update(
        {
            "Authorization": auth_header,
            "Host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
    )
    request_obj = Request(endpoint, data=data, headers=request_headers, method=method)
    return opener(request_obj, timeout=timeout)


def get_bytes(requester: SignedRequester, object_key: str, *, timeout: int = 45) -> tuple[int, bytes]:
    payload_hash = hashlib.sha256(b"").hexdigest()
    with requester("GET", object_key, payload_hash, timeout=timeout) as response:
        return response.status, response.read()


def list_object_keys(
    requester: SignedRequester,
    prefix: str,
    *,
    max_keys: int,
    continuation_token: str = "",
    timeout: int = 45,
) -> tuple[int, list[str], str]:
    payload_hash = hashlib.sha256(b"").hexdigest()
    query_params = {"list-type": "2", "prefix": prefix, "max-keys": str(max_keys)}
    if continuation_token:
        query_params["continuation-token"] = continuation_token
    with requester(
        "GET", "", payload_hash, timeout=timeout, query_params=query_params
    ) as response:
        status = response.status
        body = response.read()
    root = ET.fromstring(body)
    namespace = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    keys = [node.text for node in root.findall(f"{namespace}Contents/{namespace}Key") if node.text]
    next_token = root.findtext(f"{namespace}NextContinuationToken", default="")
    return status, keys, next_token or ""


def put_bytes(
    requester: SignedRequester,
    data: bytes,
    object_key: str,
    content_type: str,
    *,
    cache_control: str,
    timeout: int = 120,
) -> int:
    payload_hash = hashlib.sha256(data).hexdigest()
    upload_headers = {
        "Cache-Control": cache_control,
        "Content-Type": content_type or "application/octet-stream",
    }
    with requester(
        "PUT",
        object_key,
        payload_hash,
        extra_headers=upload_headers,
        data=data,
        timeout=timeout,
    ) as response:
        return response.status


def delete_object(requester: SignedRequester, object_key: str, *, timeout: int = 45) -> int:
    payload_hash = hashlib.sha256(b"").hexdigest()
    with requester("DELETE", object_key, payload_hash, timeout=timeout) as response:
        return response.status
