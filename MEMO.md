# Technical Memo

## Objective recap

Classify emotional tone/intensity and detect background noise, audio
quality, speaker overlap, and long silence in production call audio, at
≤$0.003/minute, with a hosted batch-upload dashboard.

## Approaches considered

**1. Raw audio → audio-native LLM (e.g. `gpt-4o-audio-preview`), one call
per clip, JSON output.**
Simplest to implement — no self-hosted models, no acoustic feature
engineering. Rejected on cost: OpenAI's audio-input token pricing is far
above its text-input pricing, and back-of-envelope pricing puts this
approach at roughly $0.03–0.05/minute — 10–15x over the $0.003 ceiling.
Also sends raw customer audio to a third party for every field, including
ones (noise, clipping, SNR) that don't need semantic understanding at all.

**2. Hosted transcription (`whisper-1`) → text LLM classification.**
`whisper-1` alone is a flat $0.006/minute — 2x over the ceiling before any
classification cost is added. Rejected for the same reason as #1: the cost
ceiling can't be hit with hosted per-minute ASR at these rates.

**3. (Selected) Self-hosted transcription + deterministic acoustic
features + text-only LLM call for the fields that need semantic judgment.**
- `faster-whisper` (open-source, runs on CPU) transcribes locally — no
  per-minute API cost, and raw audio never leaves the backend.
- `librosa` + `webrtcvad` compute noise presence/severity, audio quality,
  overlap, and long-silence deterministically from the waveform. These are
  acoustic/signal properties, not semantic ones — a rules-based approach is
  both cheaper and more consistent than asking an LLM to eyeball an SNR.
- `gpt-4o-mini` receives only the transcript plus a compact numeric feature
  summary (duration, noise severity, SNR, loudness) and returns
  `emotional_tone`, `emotional_intensity`, `background_noise_type`
  (free-text description), and `confidence`. Text tokens are cheap enough
  that this call costs a small fraction of the ceiling even for long clips.

This is also the two-materially-different-approaches comparison requested
in the brief: #3's acoustic-feature layer vs. an audio/LLM-based layer,
combined into one hybrid rather than run as competing alternatives, because
each half is clearly better suited to the fields it owns (see per-field
mapping below).

## Why the fields are split this way

| Field | Method | Why |
|---|---|---|
| `background_noise_present/severity` | acoustic (SNR-based) | Physically measurable from the waveform; an LLM reading a transcript has no direct signal for this. |
| `audio_quality` | acoustic (clipping + loudness + SNR) | Same — technical audio properties, not language. |
| `speaker_overlap_present` | acoustic (VAD + spectral-flatness heuristic) | Best proxy available without paying for full diarization; see limitations. |
| `long_silence_present` | acoustic (VAD silence run length) | Directly computable from voice-activity detection. |
| `emotional_tone` / `emotional_intensity` | LLM (transcript) | Requires understanding word choice, phrasing, and context — the LLM's actual strength. |
| `background_noise_type` | LLM (transcript, gated by acoustic presence) | Free-text description benefits from conversational context (e.g. a mentioned location), but is only asked for when the acoustic layer already detected noise — avoids the LLM inventing a noise type when there isn't one. |
| `confidence` | LLM, scoped to the tone/intensity judgment | The acoustic fields don't need a separate confidence score — they're not asking the model something the model can be uncertain about. |

## External API disclosure (per brief §11)

- **Model:** `gpt-4o-mini` (OpenAI), text-only calls.
- **What's sent:** transcript text + ~5 numeric acoustic features per clip.
  Raw audio is **never** sent to OpenAI.
- **Retention:** per OpenAI's standard API data usage policy — API inputs
  are not used to train OpenAI's models by default and are retained for a
  limited abuse-monitoring window unless zero-data-retention is negotiated.
  Confirm current terms before production rollout; if stricter retention
  guarantees are required, this is the one integration point to swap out
  (see next steps).
- **Pricing assumption:** see COST.md.

## Failure modes and limitations

- **Speaker overlap detection is a heuristic, not diarization.** Without
  stereo-channel separation (agent/customer on separate channels) or a
  proper diarization model, overlap is inferred from spectral-flatness
  spikes during voice-active regions. This will under-detect subtle overlap
  and can false-positive on noisy/reverberant audio. If production calls
  are recorded in stereo with agent/customer on separate channels, this
  should be swapped for a channel-comparison approach — a strictly better
  signal, and worth prioritizing first.
- **`background_noise_type` is free text and unvalidated against a fixed
  vocabulary.** The LLM may phrase the same sound differently across calls
  (e.g. "traffic noise" vs. "road noise"). Acceptable per the brief's
  "concise description" requirement, but not exact-string-matchable.
- **Acoustic thresholds (SNR cutoffs, clipping fraction, silence duration)
  were hand-tuned by inspection against only three labeled calls.** This is
  the single biggest source of overfitting risk given how little labeled
  data was available — see VALIDATION.md for the honest framing of what the
  reported numbers do and don't prove.
- **`faster-whisper` on the `base` model** trades some transcription
  accuracy for speed/cost. Emotional-tone judgments on calls with heavy
  accents, crosstalk, or very poor audio quality will be more error-prone
  because the transcript itself degrades first.
- **No diarization means tone is inferred for "the call" as a whole,** not
  attributed to a specific speaker. If a future version needs to
  distinguish agent vs. customer tone specifically, that requires speaker
  labels the current pipeline doesn't produce.
- **OpenAI account/service failure (handled).** If the OpenAI API key is
  invalid or the account runs out of billing credit, `classify()`
  (`app/pipeline/classify.py`) now catches this specifically instead of
  letting the raw SDK exception surface: transient rate-limiting gets
  retried with backoff, while quota exhaustion or an auth failure raises a
  typed `ClassificationServiceError` with a clean, non-technical message.
  `batch_processor.py` treats this as a systemic failure, not a per-file
  one — it stops processing the rest of the batch immediately (instead of
  wasting `faster-whisper` transcription time on files guaranteed to fail
  the same way) and marks the batch `failed` rather than `completed`, so
  the dashboard shows an honest top-level status instead of N identical
  cryptic per-file errors. Before this, every file would silently burn
  full transcription time before showing a raw `Error code: 429 -
  {'error': {...}}` string per row.
- **Concurrent-upload/processing safety on a memory-constrained pilot
  instance (handled).** A `t3.medium` has 4GB RAM and 2 vCPUs shared across
  Postgres, the frontend, and the backend. Uploads were previously buffered
  fully into memory before being written to disk, and batch processing had
  no concurrency limit — several large uploads or batches landing around
  the same time could OOM the instance or thrash the 2 vCPUs against each
  other, and the per-IP upload rate limit doesn't protect against this
  since it doesn't coordinate across different users. `save_upload_stream()`
  now writes uploads to disk incrementally regardless of size, and
  `process_batch()` is capped by a `threading.Semaphore` (default 2
  concurrent batches, `MAX_CONCURRENT_BATCHES` env var) — extra batches
  wait in `"pending"` for a slot rather than all running at once. See
  README's Scaling plan for the baseline-safety note and what's still
  deferred (a real worker queue) versus what's already fixed.

## Next steps with more time/data

1. Collect more labeled calls to move validation from "hand-tuned on 3
   examples" to a real held-out split with statistically meaningful
   per-class metrics.
2. If production audio is stereo (agent/customer channels), switch overlap
   detection to direct channel comparison — removes the biggest heuristic
   weak point in the pipeline.
3. Move batch processing off in-process `BackgroundTasks` onto a proper
   queue (Celery/RQ + Redis) once batch sizes or concurrency grow past what
   a single worker process should hold in memory.
4. Consider a small fine-tuned classifier (e.g. logistic regression /
   gradient boosting over the acoustic + transcript-derived features) as a
   cheaper, lower-latency alternative to the LLM call, once enough labeled
   data exists to train and validate one properly.
5. A live metrics/evaluation dashboard (accuracy trend, latency, cost
   across runs) was considered and deliberately deferred. The brief's
   validation/cost/latency deliverables (§6 items 6–8) are document
   artifacts (VALIDATION.md/LATENCY.md/COST.md), not a dashboard
   requirement, and with only 3 labeled calls there's no run-over-run trend
   for a dashboard to usefully show — a table plus confusion matrix covers
   it. Similarly, an experiment-tracking tool like MLflow was considered
   for per-call latency and rejected as unnecessary overhead at this scale:
   `scripts/evaluate.py` already times each pipeline stage directly (see
   LATENCY.md) with no added dependency or infrastructure. Both become
   worth building once labeled data grows past a handful of examples and
   there's an actual trend to monitor across many runs over time — not
   before.
6. **Broader MLOps tradeoff:** most standard MLOps machinery (model
   registry, automated retraining pipelines, feature stores, A/B/canary
   rollout of model versions) doesn't apply here as-is, because — per
   "Approaches considered" above — there is no trained model. The acoustic
   layer is fixed thresholds and the LLM layer is a fixed zero-shot prompt
   against a third-party API; nothing is fit to data, so there's nothing to
   retrain or register in the conventional sense. What *does* have a real
   MLOps analog, deferred for the same reason as items above (not enough
   labeled data or production traffic yet to justify the overhead):
   - **Versioning the things that actually change** — the acoustic
     thresholds (`acoustic_features.py`) and the classification system
     prompt (`classify.py`) are this system's closest equivalent to model
     parameters. Neither is currently versioned/tagged independently of
     the codebase's own git history; worth a lightweight changelog if
     either gets iterated on post-pilot.
   - **Evaluation as a CI gate** — `scripts/evaluate.py` is run manually
     today. Once there's more labeled data, wiring it into CI to fail a
     PR that regresses accuracy on the labeled set (vs. just running tests
     for code correctness) is the natural next step — cheap to add, not
     done yet because 3 examples make a regression gate noisy rather than
     useful.
   - **Drift from the vendor side** — `gpt-4o-mini`'s behavior isn't fully
     under this system's control; OpenAI can update the underlying model
     without a version bump on the pinned model name. Periodic
     re-validation against the labeled set (or pinning to a dated model
     snapshot if OpenAI offers one) is the mitigation, not currently
     automated.
   Each of these is real MLOps discipline, deliberately sized down to
   match a 3-example, single-pilot-instance trial rather than skipped out
   of unawareness.
