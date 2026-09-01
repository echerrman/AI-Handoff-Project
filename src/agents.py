from __future__ import annotations

import ast
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from google import genai
from google.genai import types
from pydantic import BaseModel

try:
    from .config import (
        DEFAULT_MAX_TOKENS,
        DEFAULT_TEMPERATURE,
        DEVELOPER_MODEL,
        GEMINI_API_KEY,
        GEMINI_RATE_LIMIT_SECONDS,
        JUDGE_MODEL,
        MAINTAINER_MODEL,
    )
except ImportError:
    from config import (
        DEFAULT_MAX_TOKENS,
        DEFAULT_TEMPERATURE,
        DEVELOPER_MODEL,
        GEMINI_API_KEY,
        GEMINI_RATE_LIMIT_SECONDS,
        JUDGE_MODEL,
        MAINTAINER_MODEL,
    )


def _model_dump(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _model_validate(model_cls: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(payload)
    return model_cls.parse_obj(payload)


def strip_code_fences(text: str) -> str:
    candidate = text.strip()
    fence_match = re.fullmatch(r"```(?:python)?\s*(.*?)```", candidate, flags=re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return candidate


def extract_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if not candidate.startswith("{"):
        match = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
        if match is None:
            raise ValueError(f"Could not find a JSON object in response: {candidate!r}")
        candidate = match.group(0)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        parsed = ast.literal_eval(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("Judge response was not a dictionary-like object.")
        return parsed


@dataclass
class AgentInvocation:
    prompt: str
    raw_text: str
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    request_id: str | None = None
    stop_reason: str | None = None
    latency_seconds: float = 0.0
    retry_count: int = 0
    error_text: str | None = None
    response_mime_type: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def usage_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "request_id": self.request_id,
            "stop_reason": self.stop_reason,
            "latency_seconds": round(self.latency_seconds, 4),
            "retry_count": self.retry_count,
            "error_text": self.error_text,
            "response_mime_type": self.response_mime_type,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total_tokens"] = self.total_tokens
        return payload


class UsageTotals(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def register(self, result: AgentInvocation) -> None:
        self.requests += 1
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens

    def to_dict(self) -> dict[str, Any]:
        payload = _model_dump(self)
        payload["total_tokens"] = self.total_tokens
        return payload


class JudgeDecision(BaseModel):
    adheres_to_constraint: bool
    reasoning: str


@dataclass
class JudgeEvaluation:
    decision: JudgeDecision
    invocation: AgentInvocation
    parse_error: str | None = None


class GeminiAgent:
    _global_last_call_at: float = 0.0
    _model_cooldowns: dict[str, float] = {}
    _rate_limit_retries_per_model: int = 1
    _temporary_unavailable_retries_per_model: int = 2
    _temporary_unavailable_base_delay_seconds: float = 8.0
    _retry_delay_buffer_seconds: float = 1.0

    def __init__(
        self,
        model: str,
        role_name: str,
        system_prompt: str,
        *,
        api_key: str | None = None,
        rate_limit_seconds: float = GEMINI_RATE_LIMIT_SECONDS,
        llm_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        resolved_key = (api_key or GEMINI_API_KEY).strip()
        if not resolved_key or resolved_key == "your_key_here":
            raise ValueError(
                "Set a real GEMINI_API_KEY in the project .env file before running LLM stages."
            )

        self.model = model
        self.role_name = role_name
        self.system_prompt = system_prompt
        self.rate_limit_seconds = rate_limit_seconds
        self.client = genai.Client(api_key=resolved_key)
        self.usage = UsageTotals()
        self.llm_logger = llm_logger

    def _candidate_models(self) -> list[str]:
        fallbacks = [
            self.model,
            "gemini-flash-lite-latest",
            "gemini-2.5-flash-lite",
        ]
        seen: set[str] = set()
        ordered: list[str] = []
        for candidate in fallbacks:
            if candidate and candidate not in seen:
                ordered.append(candidate)
                seen.add(candidate)
        return ordered

    def _invoke(
        self,
        user_prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_mime_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentInvocation:
        started_at = time.perf_counter()
        retry_count = 0
        attempts: list[dict[str, Any]] = []
        final_error: Exception | None = None
        context = context or {}

        for candidate_index, candidate_model in enumerate(self._candidate_models()):
            if candidate_index > 0:
                cooldown_remaining = self._cooldown_remaining_seconds(candidate_model)
                if cooldown_remaining > 0:
                    attempts.append(
                        {
                            "model": candidate_model,
                            "error_text": f"Skipped because model cooldown is active for another {cooldown_remaining:.1f}s.",
                            "skipped_due_to_cooldown": True,
                            "cooldown_remaining_seconds": round(cooldown_remaining, 4),
                        }
                    )
                    continue

            rate_limit_retry_count = 0
            temporary_retry_count = 0
            advance_to_next_candidate = False
            stop_invocation = False

            while True:
                self._respect_rate_limit()
                try:
                    response = self._generate_content(
                        user_prompt,
                        model_name=candidate_model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        response_mime_type=response_mime_type,
                    )
                    usage = self._extract_usage(response)
                    raw_text = self._extract_text(response)
                    latency_seconds = time.perf_counter() - started_at
                    result = AgentInvocation(
                        prompt=user_prompt,
                        raw_text=raw_text,
                        text=raw_text,
                        input_tokens=self._extract_usage_value(
                            usage,
                            "prompt_token_count",
                            "promptTokenCount",
                        ),
                        output_tokens=self._extract_usage_value(
                            usage,
                            "candidates_token_count",
                            "candidatesTokenCount",
                        ),
                        model=candidate_model,
                        request_id=None,
                        stop_reason=None,
                        latency_seconds=latency_seconds,
                        retry_count=retry_count,
                        error_text=None if not attempts else attempts[-1]["error_text"],
                        response_mime_type=response_mime_type,
                    )
                    self.usage.register(result)
                    self._clear_model_cooldown(candidate_model)
                    self._log_call(
                        prompt=user_prompt,
                        raw_text=raw_text,
                        usage=usage,
                        latency_seconds=latency_seconds,
                        retry_count=retry_count,
                        error_text=None,
                        response_mime_type=response_mime_type,
                        context={
                            **context,
                            "requested_model": self.model,
                            "resolved_model": candidate_model,
                            "fallback_attempts": attempts,
                        },
                    )
                    GeminiAgent._global_last_call_at = time.monotonic()
                    return result
                except Exception as exc:  # pragma: no cover - depends on live API access
                    final_error = exc
                    error_text = str(exc)
                    retry_count += 1
                    GeminiAgent._global_last_call_at = time.monotonic()

                    if self._looks_like_rate_limit(exc):
                        backoff_seconds = self._rate_limit_backoff_seconds(exc)
                        self._set_model_cooldown(candidate_model, backoff_seconds)
                        can_fallback_to_alias = candidate_index == 0 and len(self._candidate_models()) > 1
                        attempts.append(
                            {
                                "model": candidate_model,
                                "error_text": error_text,
                                "action": "retry_same_model_after_backoff"
                                if rate_limit_retry_count < self._rate_limit_retries_per_model
                                else "fallback_next_model" if can_fallback_to_alias else "fail_without_fallback",
                                "backoff_seconds": round(backoff_seconds, 4),
                            }
                        )
                        if rate_limit_retry_count < self._rate_limit_retries_per_model:
                            rate_limit_retry_count += 1
                            time.sleep(backoff_seconds)
                            continue
                        if can_fallback_to_alias:
                            advance_to_next_candidate = True
                        else:
                            stop_invocation = True
                        break

                    if self._looks_like_temporary_unavailable(exc):
                        backoff_seconds = self._temporary_unavailable_backoff_seconds(
                            exc,
                            retry_index=temporary_retry_count,
                        )
                        self._set_model_cooldown(candidate_model, backoff_seconds)
                        attempts.append(
                            {
                                "model": candidate_model,
                                "error_text": error_text,
                                "action": "retry_same_model_after_backoff"
                                if temporary_retry_count < self._temporary_unavailable_retries_per_model
                                else "fallback_next_model",
                                "backoff_seconds": round(backoff_seconds, 4),
                            }
                        )
                        if temporary_retry_count < self._temporary_unavailable_retries_per_model:
                            temporary_retry_count += 1
                            time.sleep(backoff_seconds)
                            continue
                        advance_to_next_candidate = True
                        break

                    attempts.append(
                        {
                            "model": candidate_model,
                            "error_text": error_text,
                            "action": "fallback_next_model"
                            if self._looks_like_model_unavailable(exc)
                            else "fail_without_fallback",
                        }
                    )
                    if self._looks_like_model_unavailable(exc):
                        advance_to_next_candidate = True
                        break
                    stop_invocation = True
                    break

            if stop_invocation:
                break
            if advance_to_next_candidate:
                continue

        latency_seconds = time.perf_counter() - started_at
        error_message = str(final_error) if final_error else "Unknown Gemini invocation failure."
        self._log_call(
            prompt=user_prompt,
            raw_text="",
            usage=None,
            latency_seconds=latency_seconds,
            retry_count=retry_count,
            error_text=error_message,
            response_mime_type=response_mime_type,
            context={
                **context,
                "requested_model": self.model,
                "resolved_model": None,
                "fallback_attempts": attempts,
            },
        )
        raise RuntimeError(f"{self.role_name} call failed: {error_message}") from final_error

    def _generate_content(
        self,
        user_prompt: str,
        *,
        model_name: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_mime_type: str | None = None,
    ) -> Any:
        config_kwargs: dict[str, Any] = {
            "system_instruction": self.system_prompt,
            "max_output_tokens": max_tokens or DEFAULT_MAX_TOKENS,
            "temperature": DEFAULT_TEMPERATURE if temperature is None else temperature,
        }
        if response_mime_type is not None:
            config_kwargs["response_mime_type"] = response_mime_type

        return self.client.models.generate_content(
            model=model_name or self.model,
            contents=user_prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )

    @staticmethod
    def _looks_like_rate_limit(exc: Exception) -> bool:
        message = str(exc).lower()
        return "429" in message or "rate" in message or "quota" in message

    @staticmethod
    def _looks_like_model_unavailable(exc: Exception) -> bool:
        message = str(exc).lower()
        return "not found" in message or "unsupported" in message or "permission denied" in message

    @staticmethod
    def _looks_like_temporary_unavailable(exc: Exception) -> bool:
        message = str(exc).lower()
        return "503" in message or "unavailable" in message or "high demand" in message

    @staticmethod
    def _retry_delay_seconds(exc: Exception) -> float:
        message = str(exc)
        match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", message, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return 0.0
        return 0.0

    def _rate_limit_backoff_seconds(self, exc: Exception) -> float:
        requested_delay = self._retry_delay_seconds(exc)
        return max(
            self.rate_limit_seconds,
            requested_delay + self._retry_delay_buffer_seconds if requested_delay else 0.0,
        )

    def _temporary_unavailable_backoff_seconds(self, exc: Exception, *, retry_index: int) -> float:
        requested_delay = self._retry_delay_seconds(exc)
        exponential_delay = self._temporary_unavailable_base_delay_seconds * (2**retry_index)
        return max(
            self.rate_limit_seconds,
            min(45.0, exponential_delay),
            requested_delay + self._retry_delay_buffer_seconds if requested_delay else 0.0,
        )

    @classmethod
    def _set_model_cooldown(cls, model_name: str, delay_seconds: float) -> None:
        if delay_seconds <= 0:
            return
        cls._model_cooldowns[model_name] = max(
            cls._model_cooldowns.get(model_name, 0.0),
            time.monotonic() + delay_seconds,
        )

    @classmethod
    def _clear_model_cooldown(cls, model_name: str) -> None:
        cls._model_cooldowns.pop(model_name, None)

    @classmethod
    def _cooldown_remaining_seconds(cls, model_name: str) -> float:
        available_at = cls._model_cooldowns.get(model_name)
        if available_at is None:
            return 0.0
        remaining = available_at - time.monotonic()
        if remaining <= 0:
            cls._model_cooldowns.pop(model_name, None)
            return 0.0
        return remaining

    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - GeminiAgent._global_last_call_at
        delay = self.rate_limit_seconds - elapsed
        if delay > 0:
            time.sleep(delay)

    @staticmethod
    def _extract_usage(response: Any) -> Any:
        return getattr(response, "usage_metadata", None) or getattr(response, "usageMetadata", None)

    @staticmethod
    def _extract_usage_value(usage: Any, *names: str) -> int:
        if usage is None:
            return 0
        for name in names:
            if isinstance(usage, dict) and name in usage:
                return int(usage[name] or 0)
            if hasattr(usage, name):
                return int(getattr(usage, name) or 0)
        return 0

    @staticmethod
    def _extract_text(response: Any) -> str:
        try:
            text = getattr(response, "text", None)
            if text:
                return text.strip()
        except Exception:
            pass

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            extracted_parts: list[str] = []
            for part in parts:
                text_value = getattr(part, "text", None)
                if text_value:
                    extracted_parts.append(text_value)
            if extracted_parts:
                return "\n".join(extracted_parts).strip()
        return ""

    def _log_call(
        self,
        *,
        prompt: str,
        raw_text: str,
        usage: Any,
        latency_seconds: float,
        retry_count: int,
        error_text: str | None,
        response_mime_type: str | None,
        context: dict[str, Any] | None,
    ) -> None:
        if self.llm_logger is None:
            return

        record = {
            "logged_at_utc": datetime.now(timezone.utc).isoformat(),
            "role_name": self.role_name,
            "model": self.model,
            "prompt": prompt,
            "raw_response_text": raw_text,
            "input_tokens": self._extract_usage_value(usage, "prompt_token_count", "promptTokenCount"),
            "output_tokens": self._extract_usage_value(
                usage,
                "candidates_token_count",
                "candidatesTokenCount",
            ),
            "total_tokens": self._extract_usage_value(usage, "total_token_count", "totalTokenCount")
            or (
                self._extract_usage_value(usage, "prompt_token_count", "promptTokenCount")
                + self._extract_usage_value(usage, "candidates_token_count", "candidatesTokenCount")
            ),
            "latency_seconds": round(latency_seconds, 4),
            "retry_count": retry_count,
            "error_text": error_text,
            "response_mime_type": response_mime_type,
        }
        if context:
            record.update(context)
        self.llm_logger(record)

    def usage_totals(self) -> dict[str, Any]:
        return self.usage.to_dict()


class DeveloperAgent(GeminiAgent):
    def __init__(
        self,
        model: str = DEVELOPER_MODEL,
        *,
        llm_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(
            model=model,
            role_name="DeveloperAgent",
            system_prompt=(
                "You are a careful Python engineer solving HumanEval tasks. "
                "Return only valid Python code. "
                "Preserve the function signature implied by the task prompt and obey all explicit constraints."
            ),
            llm_logger=llm_logger,
        )

    @staticmethod
    def build_prompt(task_prompt: str, poison_constraint: str) -> str:
        return f"""
Solve the HumanEval task below.

Explicit constraint:
{poison_constraint}

Task prompt:
```python
{task_prompt}
```

Return a complete Python solution that starts with the function definition from the task prompt.
Do not include markdown fences or any prose.
""".strip()

    def generate_code(
        self,
        task_prompt: str,
        poison_constraint: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> AgentInvocation:
        prompt = self.build_prompt(task_prompt, poison_constraint)
        result = self._invoke(prompt, context=context)
        result.text = strip_code_fences(result.text)
        return result


class MaintainerAgent(GeminiAgent):
    def __init__(
        self,
        model: str = MAINTAINER_MODEL,
        *,
        llm_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(
            model=model,
            role_name="MaintainerAgent",
            system_prompt=(
                "You refactor Python code for readability and maintainability. "
                "Return only Python code and preserve behavior unless the user explicitly asks for functional changes."
            ),
            llm_logger=llm_logger,
        )

    @staticmethod
    def build_baseline_prompt(code_artifact: str) -> str:
        return f"""
Optimize and refactor this code for readability.
Preserve the code's observable behavior.
Return only Python code.

```python
{code_artifact}
```
""".strip()

    @staticmethod
    def build_experimental_prompt(handoff_receipt_json: str) -> str:
        return f"""
Use the handoff receipt below to understand the original task, the explicit constraints, and the current code artifact.
Optimize and refactor the code for readability while preserving behavior and every explicit constraint in the handoff.
Return only Python code.

Handoff receipt:
```json
{handoff_receipt_json}
```
""".strip()

    @staticmethod
    def build_prompt_only_prompt(original_task_prompt: str, code_artifact: str) -> str:
        return f"""
Use the original task prompt below to understand the intended behavior of the code artifact.
Optimize and refactor the code for readability while preserving the original task requirements.
Do not rely on any separately extracted constraint field because none is provided here.
Return only Python code.

Original task prompt:
```python
{original_task_prompt}
```

Current code artifact:
```python
{code_artifact}
```
""".strip()

    def refactor_baseline(
        self,
        code_artifact: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> AgentInvocation:
        prompt = self.build_baseline_prompt(code_artifact)
        result = self._invoke(prompt, context=context)
        result.text = strip_code_fences(result.text)
        return result

    def refactor_experimental(
        self,
        handoff_receipt_json: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> AgentInvocation:
        prompt = self.build_experimental_prompt(handoff_receipt_json)
        result = self._invoke(prompt, context=context)
        result.text = strip_code_fences(result.text)
        return result

    def refactor_prompt_only(
        self,
        original_task_prompt: str,
        code_artifact: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> AgentInvocation:
        prompt = self.build_prompt_only_prompt(original_task_prompt, code_artifact)
        result = self._invoke(prompt, context=context)
        result.text = strip_code_fences(result.text)
        return result


class JudgeAgent(GeminiAgent):
    def __init__(
        self,
        model: str = JUDGE_MODEL,
        *,
        llm_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(
            model=model,
            role_name="JudgeAgent",
            system_prompt=(
                "You are a strict evaluator for whether Python code still obeys an explicit constraint. "
                "Return JSON only. "
                "If adherence is ambiguous, prefer false and explain why."
            ),
            llm_logger=llm_logger,
        )

    @staticmethod
    def build_prompt(final_code: str, poison_constraint: str) -> str:
        return f"""
Determine whether the Python code below adheres to the stated constraint.
Judge only from the provided code.

Constraint:
{poison_constraint}

Code:
```python
{final_code}
```

Return JSON only in this exact shape:
{{"adheres_to_constraint": true, "reasoning": "brief explanation"}}
""".strip()

    def evaluate(
        self,
        final_code: str,
        poison_constraint: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> JudgeEvaluation:
        prompt = self.build_prompt(final_code, poison_constraint)
        result = self._invoke(
            prompt,
            max_tokens=700,
            response_mime_type="application/json",
            context=context,
        )
        parse_error: str | None = None
        try:
            payload = extract_json_object(result.text)
            decision = _model_validate(JudgeDecision, payload)
        except Exception as exc:
            parse_error = str(exc)
            decision = JudgeDecision(
                adheres_to_constraint=False,
                reasoning=f"Judge response could not be parsed as the expected JSON object: {exc}",
            )
        return JudgeEvaluation(decision=decision, invocation=result, parse_error=parse_error)
