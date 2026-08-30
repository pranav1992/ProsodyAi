# Latency Analysis

## Status

Measured against the three real labeled production calls on 2026-08-30
(local dev machine, not the deployed EC2 instance — see caveat below).
Estimates in the table below are kept for the stage-by-stage breakdown
context, but the measured totals replace the estimated total.

## Measured per-clip latency (real calls, local run)

| Call | Audio duration | Processing time |
|---|---|---|
| `call_001.ogg` | 30.9s | 6,966ms |
| `call_002.ogg` | 35.0s | 6,958ms |
| `call_003.ogg` | 171.9s | 10,358ms |
| **Mean / max** | | **8,094ms mean / 10,358ms max** |

Notably faster than the original CPU-transcription estimate below (which
assumed 0.3–0.7x real-time on a `t3.medium`) — this run was on a local dev
machine, not the actual `t3.medium` EC2 instance, so these numbers likely
**understate** production latency. Re-run `scripts/evaluate.py` on the
deployed instance (or via SSH) before finalizing this document, since the
brief scores latency on production-realistic numbers, not dev-machine ones.

## Per-clip pipeline breakdown (measured, real calls, local run)

`scripts/evaluate.py` now times each pipeline stage individually
(`app/pipeline/pipeline.py`'s `stage_ms`), so this is measured, not
estimated:

| Stage | Mean | Max | Notes |
|---|---|---|---|
| Audio decode (ffmpeg/librosa load) | 191ms | 394ms | Fixed overhead, roughly independent of audio length for these clip sizes. |
| Acoustic feature extraction (`librosa`/`webrtcvad`) | 343ms | 852ms | CPU-cheap relative to transcription, as expected. |
| Transcription (`faster-whisper`, `base`, CPU) | 5,664ms | 8,109ms | Dominant cost, confirmed — ~85% of total processing time across the 3 calls. |
| Classification (`gpt-4o-mini` API call) | 1,231ms | 1,374ms | Network round-trip + generation; far below the old 1–3s estimate's upper bound. |
| **Total (measured, per call)** | **7,746ms** | **10,167ms** | See per-call table above. |

These numbers are **local-dev-machine**, not the deployed `t3.medium` —
they're faster than the original CPU-transcription estimate (which assumed
0.3–0.7x real-time on `t3.medium`), so treat this table as a lower bound.
Re-run `scripts/evaluate.py` on the EC2 instance to get production-realistic
numbers before finalizing.

Transcription dominates because it's the only step that isn't trivially
fast, which is the direct tradeoff for avoiding a per-minute hosted ASR API
(see COST.md) — self-hosting on CPU is slower than a hosted GPU-backed
service, but the cost savings are large enough (~17x under the API-based
alternatives) to be worth it for a **batch** workload, where this isn't a
real-time/interactive latency constraint per the brief's "reasonable for
production batch analysis" requirement.

## Batch throughput

The current implementation processes files within a batch **sequentially**
via FastAPI `BackgroundTasks` on a single worker process — no parallelism
across files yet. For a batch of N clips averaging 3 minutes each, expect
total batch wall-clock time ≈ N × (~65–125s).

This is an intentional simplification for the trial timeline, called out
in MEMO.md's next steps: the fix is either (a) a proper task queue
(Celery/RQ + Redis) with multiple worker processes, or (b) running multiple
`faster-whisper` inference calls concurrently up to the instance's CPU core
count. Either would give roughly linear speedup with worker count for a
CPU-bound, embarrassingly-parallel batch workload like this one.

## How to reproduce these measurements

```bash
cd backend
python scripts/evaluate.py path/to/labeled_calls_dir
# prints per-file duration_s, processing_ms, and a per-stage breakdown
# (audio_decode / acoustic_features / transcription / classification),
# plus mean/max across the set for both the total and each stage
```

For end-to-end dashboard latency (including upload, batch orchestration,
and DB round-trips), time a batch upload through the deployed dashboard
directly and record wall-clock time from upload confirmation to `completed`
status.
