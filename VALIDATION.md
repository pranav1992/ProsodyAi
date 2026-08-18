# Validation

## Status

This file is a template — run `backend/scripts/evaluate.py` against the
three labeled production calls once they're available locally, then paste
its output into the sections below before submission. Do not submit this
document with placeholder numbers still in it.

```bash
cd backend
python scripts/evaluate.py path/to/labeled_calls_dir
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

## Per-field accuracy (fill in after running evaluate.py)

| Field | Accuracy | Notes |
|---|---|---|
| `emotional_tone` | _/3 | |
| `emotional_intensity` | _/3 | |
| `background_noise_present` | _/3 | |
| `background_noise_severity` | _/3 | |
| `audio_quality` | _/3 | |
| `speaker_overlap_present` | _/3 | |
| `long_silence_present` | _/3 | |

## emotional_tone — macro F1 and confusion matrix

_Paste `evaluate.py` output here._

## Per-call notes

For each of the three calls, note here whether the acoustic thresholds
were tuned to make that specific call pass (a sign of overfitting to worry
about) or whether the prediction would plausibly hold under a threshold
tuned only on the other two calls.

1. `call_001`: —
2. `call_002`: —
3. `call_003`: —

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
