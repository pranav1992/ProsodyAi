"""LLM classification step: emotional tone/intensity/confidence + a free-text
noise-type description.

Deliberately narrow scope: everything that can be decided deterministically
from the waveform (noise presence/severity, audio quality, overlap, silence)
is decided in acoustic_features.py and is NOT overridden by this step. Only
the semantic judgments that genuinely benefit from language understanding --
reading tone from words/context, and describing *what* a noise sounds like --
go through the LLM. This keeps the per-call cost to a handful of short text
tokens well under the $0.003/minute ceiling. See COST.md.

Only the transcript and a small numeric feature summary are sent to OpenAI --
never the raw audio -- per the data-handling constraint in the brief.
"""
import json
import time

from openai import APIError, AuthenticationError, OpenAI, RateLimitError

from app.config import get_settings
from app.pipeline.acoustic_features import AcousticFeatures
from app.pipeline.errors import ClassificationServiceError

settings = get_settings()

# Rate-limit errors are ambiguous by exception type alone -- OpenAI raises
# the same RateLimitError class for "too many requests per minute, retry
# shortly" and "account is out of credits, retrying will never help". Only
# the `code` field on the exception (mirrors the API response body)
# distinguishes them.
_QUOTA_EXHAUSTED_CODE = "insufficient_quota"
_MAX_RETRIES = 2
_RETRY_DELAY_S = 5

SCHEMA = {
    "type": "object",
    "properties": {
        "emotional_tone": {
            "type": "string",
            "enum": ["neutral", "satisfied", "frustrated", "upset", "distressed"],
        },
        "emotional_intensity": {"type": "string", "enum": ["low", "medium", "high"]},
        "background_noise_type": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["emotional_tone", "emotional_intensity", "background_noise_type", "confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You classify the emotional tone of a customer on a support call \
transcript, and briefly describe any background noise, for a production call-analytics \
system. Use ONLY the definitions below -- do not invent your own criteria.

emotional_tone:
- neutral: no clear positive or negative emotion.
- satisfied: pleased, relieved, appreciative, or clearly positive.
- frustrated: annoyed, impatient, or dissatisfied without strong anger or distress.
- upset: clearly angry, agitated, or strongly dissatisfied.
- distressed: highly emotional, overwhelmed, panicked, crying, or otherwise emotionally escalated.

emotional_intensity:
- low: subtle or mild.
- medium: clear and sustained.
- high: strong, escalated, or likely to require attention.

Do NOT infer frustration or distress solely from loudness -- loudness is reported to you only
as a acoustic feature for context, not as evidence of emotion by itself. Base tone/intensity on
the words, phrasing, and conversational context in the transcript.

background_noise_type: a short, concrete phrase describing the dominant background sound if the
acoustic analysis detected noise (e.g. "office chatter", "music", "road noise", "television",
"keyboard typing", "wind", "mechanical noise"). If the acoustic analysis found no noise, return
an empty string, regardless of transcript content.

confidence: your confidence (0.0-1.0) in the emotional_tone/emotional_intensity judgment given
the available transcript. Lower confidence for short, ambiguous, or noisy-transcript clips.

Respond only with the JSON object matching the given schema."""


def _client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def _create_completion(user_content: str):
    kwargs = dict(
        model=settings.classification_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "call_classification", "schema": SCHEMA, "strict": True},
        },
        temperature=0,
    )

    for attempt in range(_MAX_RETRIES + 1):
        try:
            return _client().chat.completions.create(**kwargs)
        except AuthenticationError as exc:
            raise ClassificationServiceError(
                "Classification service is misconfigured (invalid OpenAI API key). "
                "Contact your administrator."
            ) from exc
        except RateLimitError as exc:
            if exc.code == _QUOTA_EXHAUSTED_CODE:
                raise ClassificationServiceError(
                    "Classification service is unavailable: the OpenAI account has "
                    "run out of credits. Contact your administrator to add billing "
                    "credit, then re-run this batch."
                ) from exc
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_S)
                continue
            raise ClassificationServiceError(
                "Classification service is rate-limited and retries were "
                "exhausted. Try again in a few minutes."
            ) from exc
        except APIError as exc:
            # Connection errors, 5xx from OpenAI, etc -- not specific to this
            # file either, but worth one retry since these are often transient.
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_S)
                continue
            raise ClassificationServiceError(
                f"Classification service error: {exc.message}"
            ) from exc


def classify(transcript: str, features: AcousticFeatures) -> tuple[dict, dict]:
    feature_summary = (
        f"duration_seconds={features.duration_s:.1f}, "
        f"background_noise_detected={features.background_noise_present}, "
        f"background_noise_severity={features.background_noise_severity}, "
        f"estimated_snr_db={features.snr_db:.1f}, "
        f"mean_loudness_dbfs={features.mean_rms_dbfs:.1f}"
    )
    user_content = (
        f"Acoustic analysis (already computed, do not re-derive noise presence/severity):\n"
        f"{feature_summary}\n\n"
        f"Transcript:\n{transcript or '[no speech detected / empty transcript]'}"
    )

    response = _create_completion(user_content)
    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
    }
    return json.loads(response.choices[0].message.content), usage
