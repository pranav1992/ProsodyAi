import json
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIConnectionError, AuthenticationError, RateLimitError

from app.pipeline import classify as classify_module
from app.pipeline.acoustic_features import AcousticFeatures
from app.pipeline.errors import ClassificationServiceError


def _features() -> AcousticFeatures:
    return AcousticFeatures(
        duration_s=3.0,
        speech_ratio=0.8,
        longest_silence_s=0.5,
        long_silence_present=False,
        speaker_overlap_present=False,
        overlap_ratio=0.0,
        snr_db=20.0,
        clipping_fraction=0.0,
        mean_rms_dbfs=-20.0,
        spectral_flatness=0.3,
        background_noise_present=False,
        background_noise_severity="none",
        audio_quality="clear",
    )


def _status_error(cls, code: str, message: str):
    """Build a real openai.<cls> the way the SDK would, so exc.code is
    populated exactly like it is against the live API."""
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(status_code=cls.status_code, request=request)
    body = {"message": message, "type": "error", "code": code, "param": None}
    return cls(message, response=response, body=body)


def _fake_completion() -> MagicMock:
    completion = MagicMock()
    completion.choices[0].message.content = json.dumps({
        "emotional_tone": "neutral",
        "emotional_intensity": "low",
        "background_noise_type": "",
        "confidence": 0.5,
    })
    completion.usage.prompt_tokens = 100
    completion.usage.completion_tokens = 10
    return completion


def _patch_client(monkeypatch, create_mock):
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(classify_module, "_client", lambda: fake_client)
    monkeypatch.setattr(classify_module.time, "sleep", lambda _seconds: None)
    return fake_client


def test_auth_error_raises_clean_message_without_retry(monkeypatch):
    exc = _status_error(AuthenticationError, "invalid_api_key", "Incorrect API key provided")
    create_mock = MagicMock(side_effect=exc)
    _patch_client(monkeypatch, create_mock)

    with pytest.raises(ClassificationServiceError) as exc_info:
        classify_module.classify("hello", _features())

    assert "misconfigured" in exc_info.value.user_message
    assert "administrator" in exc_info.value.user_message
    assert create_mock.call_count == 1  # not retryable -- no point retrying a bad key


def test_quota_exhausted_raises_clean_message_without_retry(monkeypatch):
    exc = _status_error(RateLimitError, "insufficient_quota", "You exceeded your current quota")
    create_mock = MagicMock(side_effect=exc)
    _patch_client(monkeypatch, create_mock)

    with pytest.raises(ClassificationServiceError) as exc_info:
        classify_module.classify("hello", _features())

    assert "run out of credits" in exc_info.value.user_message
    assert create_mock.call_count == 1  # retrying won't add credits -- must not retry


def test_transient_rate_limit_retries_then_succeeds(monkeypatch):
    exc = _status_error(RateLimitError, "rate_limit_exceeded", "Rate limit reached for requests")
    create_mock = MagicMock(side_effect=[exc, exc, _fake_completion()])
    _patch_client(monkeypatch, create_mock)

    result, usage = classify_module.classify("hello", _features())

    assert result["emotional_tone"] == "neutral"
    assert usage == {"prompt_tokens": 100, "completion_tokens": 10}
    assert create_mock.call_count == 3  # 2 failures + 1 success, within the retry budget


def test_transient_rate_limit_raises_after_exhausting_retries(monkeypatch):
    exc = _status_error(RateLimitError, "rate_limit_exceeded", "Rate limit reached for requests")
    create_mock = MagicMock(side_effect=exc)
    _patch_client(monkeypatch, create_mock)

    with pytest.raises(ClassificationServiceError) as exc_info:
        classify_module.classify("hello", _features())

    assert "retries were exhausted" in exc_info.value.user_message
    assert create_mock.call_count == classify_module._MAX_RETRIES + 1


def test_connection_error_retries_then_raises_with_openai_message(monkeypatch):
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    exc = APIConnectionError(message="Connection error.", request=request)
    create_mock = MagicMock(side_effect=exc)
    _patch_client(monkeypatch, create_mock)

    with pytest.raises(ClassificationServiceError) as exc_info:
        classify_module.classify("hello", _features())

    assert "Connection error" in exc_info.value.user_message
    assert create_mock.call_count == classify_module._MAX_RETRIES + 1
