# gpt-4o-mini standard pricing, verified against platform.openai.com/docs/pricing
# on 2026-08-30. Re-check before relying on this for a final cost figure --
# OpenAI's rates change over time. See COST.md.
INPUT_RATE_PER_TOKEN = 0.15 / 1_000_000
OUTPUT_RATE_PER_TOKEN = 0.60 / 1_000_000


def classification_cost_usd(usage: dict) -> float:
    return (
        usage["prompt_tokens"] * INPUT_RATE_PER_TOKEN
        + usage["completion_tokens"] * OUTPUT_RATE_PER_TOKEN
    )
