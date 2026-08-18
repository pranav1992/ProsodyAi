# Latency Analysis

## Status

Estimates below are based on typical component-level performance
characteristics; replace with measured numbers from `scripts/evaluate.py`
(which prints per-file `processing_ms`) once run against real audio, and
from the deployed Render instance under realistic load.

## Per-clip pipeline breakdown (estimated)

| Stage | Estimated time (3-minute call) | Notes |
|---|---|---|
| ffmpeg decode/resample | ~0.2–0.5s | Fixed overhead, roughly independent of audio length for short clips. |
| Acoustic feature extraction (`librosa`/`webrtcvad`) | ~0.5–1.5s | Runs on the full waveform; scales roughly linearly with audio length but is CPU-cheap relative to transcription. |
| Transcription (`faster-whisper`, `base`, CPU) | ~60–120s | Dominant cost. Roughly 0.3–0.7x real-time on typical Render CPU instances — i.e., a 3-minute call takes 1–2 minutes to transcribe. Update after measuring on the actual deployed instance size. |
| Classification (`gpt-4o-mini` API call) | ~1–3s | Network round-trip + generation time for a short JSON response; largely independent of audio length. |
| **Total per 3-minute call** | **~65–125s** | |

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
# prints per-file duration_s and processing_ms, plus mean/max across the set
```

For end-to-end dashboard latency (including upload, batch orchestration,
and DB round-trips), time a batch upload through the deployed dashboard
directly and record wall-clock time from upload confirmation to `completed`
status.
