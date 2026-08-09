"""Narration generation and signed draft-domain helpers."""

from __future__ import annotations

import base64
import io
import json
import re
import wave
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


class GeminiTTSError(RuntimeError):
    pass


class NarrationDraftError(RuntimeError):
    pass


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, sample_width: int = 2) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return output.getvalue()


def parse_audio_mime_type(mime_type: str | None) -> tuple[int, int, int]:
    mime = str(mime_type or "").lower()
    rate_match = re.search(r"(?:rate|samplerate)=(\d+)", mime)
    channels_match = re.search(r"channels=(\d+)", mime)
    return int(rate_match.group(1)) if rate_match else 24000, int(channels_match.group(1)) if channels_match else 1, 2


def convert_to_wav(audio_data: bytes, mime_type: str | None) -> tuple[bytes, str]:
    mime = str(mime_type or "").lower()
    formats = (("audio/wav", ".wav"), ("audio/x-wav", ".wav"), ("audio/mpeg", ".mp3"), ("audio/mp3", ".mp3"), ("audio/ogg", ".ogg"), ("application/ogg", ".ogg"), ("audio/mp4", ".m4a"), ("audio/x-m4a", ".m4a"))
    for prefix, extension in formats:
        if mime.startswith(prefix):
            return audio_data, extension
    return pcm_to_wav(audio_data, *parse_audio_mime_type(mime)), ".wav"


def generate_gemini_tts_audio(text: str, api_key: str, *, opener=urlopen) -> tuple[bytes, str]:
    if not api_key:
        raise GeminiTTSError("GEMINI_API_KEY is not configured")
    prompt = "อ่านคำบรรยายต่อไปนี้เป็นภาษาไทย น้ำเสียงชัดเจน เป็นมิตร เหมาะกับนิทรรศการและแหล่งเรียนรู้ เว้นจังหวะพอดี:\n" + text.strip()
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Iapetus"}}}}}
    request_obj = Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-tts-preview:generateContent",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST",
    )
    try:
        with opener(request_obj, timeout=90) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace").strip()
        raise GeminiTTSError(f"Gemini API returned HTTP {exc.code}: {detail or exc.reason}") from exc
    except URLError as exc:
        raise GeminiTTSError(f"Gemini API connection failed: {exc.reason}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise GeminiTTSError("Gemini API returned an invalid response") from exc
    try:
        part = response_data["candidates"][0]["content"]["parts"][0]["inlineData"]
        audio_data = base64.b64decode(part["data"], validate=True)
        mime_type = str(part.get("mimeType") or "")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GeminiTTSError("Gemini did not return audio data") from exc
    if not audio_data:
        raise GeminiTTSError("Gemini did not return audio data")
    return convert_to_wav(audio_data, mime_type)


def serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt="armodel-narration-draft-v1")


def load_token(token: str, secret_key: str, max_age: int, pending_prefix: str) -> dict:
    try:
        payload = serializer(secret_key).loads(token, max_age=max_age)
    except SignatureExpired as exc:
        raise NarrationDraftError("เสียงรอตรวจสอบหมดอายุแล้ว กรุณาสร้างใหม่") from exc
    except BadSignature as exc:
        raise NarrationDraftError("ข้อมูลเสียงรอตรวจสอบไม่ถูกต้อง") from exc
    if not isinstance(payload, dict):
        raise NarrationDraftError("ข้อมูลเสียงรอตรวจสอบไม่ถูกต้อง")
    key = str(payload.get("pending_key") or "")
    if not str(payload.get("model_id") or "") or not (key.startswith(pending_prefix) or key.startswith("local-pending/")):
        raise NarrationDraftError("ข้อมูลเสียงรอตรวจสอบไม่ถูกต้อง")
    return payload


def local_draft_path(root: Path, key: str) -> Path:
    if not key.startswith("local-pending/"):
        raise NarrationDraftError("ตำแหน่งไฟล์รอตรวจสอบไม่ถูกต้อง")
    target = (root / Path(key.removeprefix("local-pending/"))).resolve()
    resolved_root = root.resolve()
    if resolved_root not in target.parents:
        raise NarrationDraftError("ตำแหน่งไฟล์รอตรวจสอบไม่ถูกต้อง")
    return target


def owned_r2_key(audio_url: str, public_base: str, permanent_prefix: str) -> str:
    base = public_base.rstrip("/")
    if not base or not audio_url.startswith(f"{base}/"):
        return ""
    key = audio_url.removeprefix(f"{base}/")
    return key if key.startswith(permanent_prefix) else ""
