import pytest

from armodel.services import narration


def test_audio_conversion_preserves_supported_formats_and_wraps_pcm():
    assert narration.convert_to_wav(b"mp3", "audio/mpeg") == (b"mp3", ".mp3")
    wav, extension = narration.convert_to_wav(b"\x00\x00" * 10, "audio/L16;rate=16000;channels=1")
    assert extension == ".wav"
    assert wav.startswith(b"RIFF")


def test_signed_draft_token_validates_model_and_pending_prefix():
    secret = "test-secret"
    valid = narration.serializer(secret).dumps({"model_id": "m1", "pending_key": "audio/pending/m1/a.wav"})
    assert narration.load_token(valid, secret, 1800, "audio/pending/")["model_id"] == "m1"
    invalid_prefix = narration.serializer(secret).dumps({"model_id": "m1", "pending_key": "arbitrary/a.wav"})
    with pytest.raises(narration.NarrationDraftError):
        narration.load_token(invalid_prefix, secret, 1800, "audio/pending/")
    with pytest.raises(narration.NarrationDraftError):
        narration.load_token(valid + "x", secret, 1800, "audio/pending/")


def test_local_pending_path_rejects_traversal(tmp_path):
    path = narration.local_draft_path(tmp_path, "local-pending/m1/a.wav")
    assert tmp_path.resolve() in path.parents
    with pytest.raises(narration.NarrationDraftError):
        narration.local_draft_path(tmp_path, "local-pending/../../outside.wav")


def test_owned_r2_key_never_accepts_external_or_pending_urls():
    base = "https://assets.example"
    assert narration.owned_r2_key(
        f"{base}/audio/narrations/m1/a.wav", base, "audio/narrations/"
    ) == "audio/narrations/m1/a.wav"
    assert narration.owned_r2_key("https://external.example/a.wav", base, "audio/narrations/") == ""
    assert narration.owned_r2_key(f"{base}/audio/pending/m1/a.wav", base, "audio/narrations/") == ""
