# Cost Analysis

**Ceiling: $0.003/minute of audio analyzed.**

⚠️ The OpenAI per-token rates used below are illustrative placeholders based
on `gpt-4o-mini`'s general pricing tier at the time this was written — verify
the exact current rate on OpenAI's pricing page before finalizing this
document, since API pricing changes over time and this number should not be
submitted without a live check.

## Cost components

There are two components, and only one of them is a per-minute API cost —
the other is amortized compute infrastructure, which is the whole point of
self-hosting the transcription step (see MEMO.md for why).

### 1. Transcription (`faster-whisper`, self-hosted — compute cost, not API)

No per-call charge from a vendor. Cost is the marginal compute time on the
Render instance running the backend, amortized over instance uptime cost.

Assumptions:
- Render "standard" web service instance: ~$25/month → $0.0342/hour of
  instance uptime.
- `faster-whisper` `base` model on CPU processes audio at roughly 2x
  real-time (i.e., transcribing 1 minute of audio takes ~30 seconds of
  compute) — actual ratio depends on instance CPU; measure and update once
  deployed (see LATENCY.md).
- Instance cost is shared across all processing that instance does, so this
  is a rough allocation, not a hard metered cost like a per-minute API.

Estimated: $0.0342/hr ÷ 60 min/hr × 0.5 min compute per min of audio
≈ **$0.00029 per minute of audio**.

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

### Combined estimate

| Component | Cost per audio-minute |
|---|---|
| Self-hosted transcription (amortized compute) | ≈ $0.00029 |
| `gpt-4o-mini` classification call | ≈ $0.00006 |
| **Total** | **≈ $0.00035** |

That's roughly **8–9x under** the $0.003/minute ceiling, leaving headroom
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
- Confirm OpenAI's current `gpt-4o-mini` pricing and, if it has moved
  materially, redo the worked example above.
