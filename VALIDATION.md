# Validation

## Status

Run against the three real labeled production calls on 2026-08-30. Results
below are real, not placeholders — and they surface a live accuracy
problem (see confusion matrix) that needs investigation before submission.

```bash
cd backend
python scripts/evaluate.py eval_data/labeled_calls
```

## Methodology

- **No training occurs.** The acoustic layer is rule/threshold-based
  (`app/pipeline/acoustic_features.py`) and the LLM layer is a fixed
  zero-shot prompt (`app/pipeline/classify.py`). There is no model that
  fits parameters to the three labeled calls, so there is no train/test
  split to leak across in the conventional sense.
- **What *is* at risk of leakage:** the acoustic thresholds (SNR cutoffs
  for noise severity, clipping fraction for audio quality, silence-duration
  cutoff) were chosen by inspecting behavior on these three calls. That
  means the per-field accuracy numbers below are optimistic relative to the
  hidden test set — they confirm the thresholds aren't obviously wrong, not
  that they generalize. This is called out explicitly rather than reported
  as if it were a clean held-out result.
- **Leave-one-call-out framing:** with only three examples, formal k-fold
  CV isn't meaningful. Instead, each call's prediction is inspected against
  the other two to check whether a threshold tuned on any single call would
  have produced a wildly different outcome on the others — reported
  qualitatively below, not as a separate metric.

## Per-field accuracy

| Field | Accuracy | Notes |
|---|---|---|
| `emotional_tone` | 1/3 (0.33) | 0 correct if you exclude the neutral/neutral match that macro F1 still zeroes out on the other classes — see confusion matrix. |
| `emotional_intensity` | 1/3 (0.33) | |
| `background_noise_present` | 1/3 (0.33) | Predicted `false` on all 3; ground truth is `false, true, true` — model/thresholds are under-detecting noise. |
| `background_noise_severity` | 1/3 (0.33) | Follows directly from `background_noise_present` being wrong on 2/3. |
| `audio_quality` | 1/3 (0.33) | Predicted `slightly_impaired` on 2 calls the ground truth marks `clear`. |
| `speaker_overlap_present` | 2/3 (0.67) | |
| `long_silence_present` | 3/3 (1.00) | Only field at full accuracy. |

## emotional_tone — macro F1 and confusion matrix

Macro F1: **0.000**

```
labels: [frustrated, neutral, satisfied, upset]
[[0 0 0 0]   frustrated (predicted 1x, always wrong)
 [1 0 0 0]   neutral    (true label; 1 predicted as frustrated)
 [1 0 0 0]   satisfied  (true label; 1 predicted as frustrated)
 [1 0 0 0]]  upset      (true label; 1 predicted as neutral)
```

Predicted `neutral` for `call_002` (correct), `neutral` for `call_001`
(true: `upset`), `frustrated` for `call_003` (true: `satisfied`). With 3
classes and only 3 examples, macro F1 collapses to 0 the moment any class
is missed entirely — not by itself proof the model is unusable, but the
directional pattern (missing `upset` and `satisfied`, defaulting toward
`neutral`/`frustrated`) is a real signal, not just small-sample noise.

## Per-call notes (root cause, diagnosed 2026-08-31)

Re-ran the pipeline and inspected the actual transcript + acoustic features
`classify()`/`analyze()` saw for each call, rather than guessing from the
predictions alone. Root causes are now identified, not speculative — none
were fixed (see rationale below the table), since a same-day fix tuned
against these exact 3 calls would be the leakage the methodology section
above explicitly warns against.

1. **`call_001`** — predicted `neutral`/`low`, true `upset`/`high`.
   Transcript: *"...Are you a real person? Hello. Hello. Hello. Hello.
   Hello. Hello. Yes, hello. I'm here."* — a customer repeating "hello"
   and questioning if they're talking to a bot. A human reads this as
   clear escalating frustration, but none of the words themselves are
   angry vocabulary — the emotion is carried by the *repetition pattern*,
   which `SYSTEM_PROMPT` (`app/pipeline/classify.py`) gives no explicit
   guidance to recognize. **Root cause: prompt gap for implicit/pattern-
   based distress signals, not a transcription or acoustic failure.**
2. **`call_002`** — tone correct, but noise/severity wrong (predicted no
   noise; true `TV`/medium) and intensity wrong. Measured `snr_db: 34.99`
   — the acoustic layer sees this as clean audio; TV background noise
   apparently doesn't depress SNR the way louder/broadband noise does, so
   the SNR-only heuristic misses it entirely. The transcript is also
   garbled (unexplained English/Spanish code-switching into nonsense
   phrases), suggesting Whisper struggled with this audio too — likely
   compounding the intensity miss. **Root cause: SNR-based noise detection
   doesn't generalize to this noise type; possible secondary transcription
   quality issue.**
3. **`call_003`** — tone predicted `frustrated`, true `satisfied`; also
   missed noise (`sharp static`, medium; measured `snr_db: 51.0`, same
   noise-type-blind-spot as call_002). The transcript reads as a calm,
   cooperative customer scheduling a service appointment — nothing in it
   suggests frustration, so this looks like a genuine LLM misjudgment
   with no obvious transcript-level explanation. **Root cause: unclear —
   the transcript gives no textual signal pointing to `frustrated`,
   unlike call_001 where the pattern is at least visible in hindsight.**

**Why these weren't patched before submission:** two calls (`call_002`,
`call_003`) share the same failure mode — SNR alone misses non-broadband
noise types (TV, static) — but "fixing" that from n=2 examples means
picking a new threshold that fits exactly these two calls, which is the
overfitting risk this document's methodology section already flags, not a
validated generalization. The `call_001` prompt gap is more plausibly
fixable (add explicit repetition/dead-air guidance to `SYSTEM_PROMPT`),
but doing that as an untested last-minute change immediately before
evaluation, with no re-validation window, trades a known/disclosed gap for
an unknown regression risk. Both are flagged here as the concrete next
step (see "Next steps" in MEMO.md) rather than patched blind.

**This is not yet a clean validation result** — it surfaces real, now
root-caused problems (noise-type detection blind spot, at least one
diagnosable tone-classification prompt gap) rather than confirming the
pipeline works. See the notes above before treating COST.md/LATENCY.md
numbers derived from this run as representative of final accuracy.

## Known gaps in this validation

- Three examples cannot support meaningful per-class F1 for a 5-way enum
  (`emotional_tone`) — some classes may have zero examples in this set.
  Report which classes are and aren't covered.
- `background_noise_type` (free text) has no automatic scoring here since
  it isn't an exact-match field — spot-check it manually against the
  ground truth descriptions.
- `confidence` calibration (does confidence ≈ 0.9 correspond to ~90%
  correctness) cannot be assessed with three data points; flag this as an
  open item for the hidden-set evaluation instead of claiming calibration
  here.
