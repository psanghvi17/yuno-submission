from decimal import Decimal
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

# Approximate USD per 1K tokens (gpt-4o-mini class models)
_DEFAULT_PROMPT_COST_PER_1K = Decimal("0.00015")
_DEFAULT_COMPLETION_COST_PER_1K = Decimal("0.0006")


def estimate_cost_usd(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    mock: bool = False,
) -> Decimal:
    if mock:
        return Decimal("0")
    prompt_cost = (Decimal(prompt_tokens) / 1000) * _DEFAULT_PROMPT_COST_PER_1K
    completion_cost = (Decimal(completion_tokens) / 1000) * _DEFAULT_COMPLETION_COST_PER_1K
    return prompt_cost + completion_cost


class UsageAccumulator:
    """Collects token usage across one agent invocation."""

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion


class RunUsageCallbackHandler(BaseCallbackHandler):
    """LangChain callback that records token usage from LLM responses."""

    def __init__(self, accumulator: UsageAccumulator) -> None:
        self.accumulator = accumulator

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        if not response.llm_output:
            return
        usage = response.llm_output.get("token_usage") or response.llm_output.get("usage")
        if not usage:
            return
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        self.accumulator.add(prompt, completion)
