# Cost Analysis

**Ceiling: $0.003/minute of audio analyzed.**

The `gpt-4o-mini` rates below ($0.15/1M input, $0.60/1M output) were
verified against platform.openai.com/docs/pricing on 2026-08-30 — not
placeholders. `scripts/evaluate.py` now also measures the classification
cost directly from real OpenAI API usage on every run (see "Measured"
below), so this is no longer estimate-only.

## Cost components

There are two components, and only one of them is a per-minute API cost —
the other is amortized compute infrastructure, which is the whole point of
self-hosting the transcription step (see MEMO.md for why).

### 1. Transcription (`faster-whisper`, self-hosted — compute cost, not API)

No per-call charge from a vendor. Cost is the marginal compute time on the
EC2 instance running the backend, amortized over instance uptime cost.

Assumptions:
- EC2 `t3.medium` on-demand: ~$0.0416/hour of instance uptime (⚠️ verify
  current on-demand rate for your region before finalizing this document).
- `faster-whisper` `base` model on CPU processes audio at roughly 2x
  real-time (i.e., transcribing 1 minute of audio takes ~30 seconds of
  compute) — actual ratio depends on instance CPU; measure and update once
  deployed (see LATENCY.md).
- Instance cost is shared across all processing that instance does, so this
  is a rough allocation, not a hard metered cost like a per-minute API.

Estimated: $0.0416/hr ÷ 60 min/hr × 0.5 min compute per min of audio
≈ **$0.00035 per minute of audio**.

### 2. Classification (`gpt-4o-mini`, OpenAI API — metered per token)

Only transcript text + a short numeric feature summary is sent — no audio
tokens, which is what keeps this cheap (see MEMO.md, approach comparison).

Assumptions per call:
- ~130 words/minute of speech ≈ ~170 tokens/minute of audio for the
  transcript.
- Fixed system prompt + feature summary ≈ 450 tokens (roughly constant
  regardless of call length).
- Output: a small JSON object ≈ 50 tokens.
- Illustrative rate: $0.15 / 1M input tokens, $0.60 / 1M output tokens
  (⚠️ verify current pricing).

Worked example, 3-minute call:
- Input tokens ≈ 450 + (170 × 3) = 960
- Output tokens ≈ 50
- Cost ≈ (960 × $0.15 + 50 × $0.60) / 1,000,000 ≈ **$0.00017 total**, or
  ≈ **$0.00006 per minute of audio**.

### Measured: classification cost (real run, 2026-08-30)

`scripts/evaluate.py` now reads `response.usage` from the actual OpenAI API
call and computes cost directly — no longer estimated. Run against the
three real labeled calls (3.96 audio-minutes total):

- Total: $0.000344 for 3.96 audio-minutes
- **Per audio-minute: $0.000087** — close to the $0.00006 estimate above,
  slightly higher (real transcripts run a bit longer than the 130wpm
  assumption on some calls).

This number is now trustworthy without caveats — it's not a projection. The
transcription-compute figure below is still an amortized estimate, since
that cost isn't a metered per-call charge the way the OpenAI cost is.

### Combined estimate

| Component | Cost per audio-minute | Source |
|---|---|---|
| Self-hosted transcription (amortized compute) | ≈ $0.00035 | estimated (see above, still needs real EC2 utilization data) |
| `gpt-4o-mini` classification call | **$0.000087** | measured, real API usage |
| **Total** | **≈ $0.00044** | |

That's roughly **7x under** the $0.003/minute ceiling, leaving headroom
for: a larger/more accurate Whisper model, retry logic on transient API
failures, or lower instance utilization than the amortization assumption
above assumes (i.e., the instance isn't running at 100% audio-processing
duty cycle).

## What would blow the budget (and was rejected for that reason)

- Sending raw audio to an audio-native LLM (`gpt-4o-audio-preview` or
  similar): audio-input token pricing is priced far above text, landing
  around $0.03–0.05/minute in back-of-envelope estimates — 10-15x over
  budget.
- Hosted transcription APIs billed per audio-minute (e.g. `whisper-1` at a
  flat $0.006/minute): already 2x the entire ceiling before classification
  cost is added.

## Sensitivity / caveats

- The compute-amortization figure is the least certain number here — it
  depends on actual instance utilization, which isn't known until this runs
  in production. Under low utilization (instance idle most of the time),
  effective cost per processed minute rises; under high utilization it
  falls. Re-measure after real traffic and update this document.
- `gpt-4o-mini` pricing is now verified and measured directly, not
  estimated — re-run `scripts/evaluate.py` periodically if OpenAI changes
  pricing, since the rate is hardcoded in `app/pipeline/cost.py`.
