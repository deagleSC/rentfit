"""call_structured against a fake OpenRouter: validation retry, NeedsReview, cache, budget,
rate limits and deadlines (backend plan §11.2, contract-test style)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.core.config import get_settings
from app.llm import budget
from app.llm.errors import BudgetExhausted, NeedsReview, RateLimited, TimeBudgetExceeded
from app.llm.prompts import load_all
from app.llm.prompts.smoke import ExtractInput, ExtractOutput
from app.llm.wrapper import call_structured, deadline_in
from tests.llm.conftest import tool_response

load_all()

INPUT = ExtractInput(description="2BHK in Whitefield, 35k rent, 2 months deposit, semi furnished.")
GOOD = {"bhk": 2, "rent": 35000, "deposit_months": 2, "furnishing": "semi", "locality": "Whitefield"}


@pytest.fixture(autouse=True)
def roomy_budget(db, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_daily_cap", 100)
    monkeypatch.setattr(s, "llm_structured_models", ["a:free", "b:free"])


async def call(router, **kw):
    return await call_structured("structured", "smoke_extract", INPUT, deadline=deadline_in(60),
                                 client=router.client(), **kw)


async def test_valid_tool_call_is_returned_and_cached(router):
    router.reply(tool_response(GOOD))
    res = await call(router)
    assert isinstance(res.value, ExtractOutput)
    assert res.value.rent == 35000
    assert (res.cached, res.attempts, res.model_id, res.prompt_version) == (False, 1, "a:free", 1)

    again = await call(router)  # no queued response: a model call would fail the test
    assert again.cached and again.value == res.value


async def test_request_carries_fallback_models_and_forced_tool(router):
    router.reply(tool_response(GOOD))
    await call(router, cache_enabled=False)
    body = router.requests[0]
    assert body["model"] == "a:free"
    assert body["models"] == ["a:free", "b:free"]
    assert body["tool_choice"] == {"type": "function", "function": {"name": "submit"}}
    assert body["tools"][0]["function"]["parameters"]["title"] == "ExtractOutput"


async def test_invalid_output_is_retried_once_with_the_error(router):
    router.reply(tool_response({**GOOD, "bhk": 40}))
    router.reply(tool_response(GOOD))
    res = await call(router)
    assert res.attempts == 2
    retry_msg = router.requests[1]["messages"][-1]["content"]
    assert "did not match the required schema" in retry_msg
    assert await budget.used_today() == 2  # both HTTP requests count


async def test_two_invalid_outputs_need_review(router):
    router.reply(tool_response("not json"))
    router.reply(tool_response({"bhk": "nope"}))
    with pytest.raises(NeedsReview) as exc:
        await call(router)
    assert exc.value.prompt_id == "smoke_extract"


async def test_json_in_content_is_accepted_when_model_ignores_tools(router):
    body = tool_response(GOOD)
    fenced = "```json\n" + json.dumps(GOOD) + "\n```"
    body["choices"][0]["message"] = {"role": "assistant", "content": fenced}
    router.reply(body)
    assert (await call(router)).value.locality == "Whitefield"


async def test_provider_429_raises_rate_limited(router):
    router.reply({"error": {"message": "slow down"}}, status=429, headers={"retry-after": "7"})
    with pytest.raises(RateLimited) as exc:
        await call(router)
    assert exc.value.retry_after == 7


async def test_provider_daily_limit_is_budget_exhausted_not_busy(router):
    router.reply({"error": {"message": "Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day",
                            "code": 429, "metadata": {"limit_source": "openrouter_free_tier_daily"}}}, status=429)
    with pytest.raises(BudgetExhausted):
        await call(router)


async def test_empty_completion_raises_rate_limited(router):
    body = tool_response(GOOD)
    body["choices"] = []
    router.reply(body)
    with pytest.raises(RateLimited):
        await call(router)


async def test_exhausted_budget_makes_no_model_call(router, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_daily_cap", 0)
    with pytest.raises(BudgetExhausted):
        await call(router)
    assert router.requests == []


async def test_no_time_left_makes_no_model_call(router):
    with pytest.raises(TimeBudgetExceeded):
        await call_structured("structured", "smoke_extract", INPUT, deadline=deadline_in(1), client=router.client())
    assert router.requests == []


async def test_fallback_model_is_recorded(router, db):
    router.reply(tool_response(GOOD, model="b:free"))
    res = await call(router, cache_enabled=False)
    assert res.model_id == "b:free"
    rows = await db.fetchall("select requests_used from llm_budget where model_id = 'b:free' and day = current_date")
    assert rows[0]["requests_used"] == 1


async def test_sync_calls_use_the_rpm_bucket(router, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_sync_rpm_cap", 1)
    # Pin the clock: crossing a minute boundary between the two calls would open a fresh bucket.
    fixed = datetime(2030, 1, 1, 12, 0, 30, tzinfo=UTC)
    real_throttle = budget.throttle
    monkeypatch.setattr(budget, "throttle", lambda cap=None, now=None: real_throttle(cap, now=fixed))
    router.reply(tool_response(GOOD))
    await call(router, sync=True, cache_enabled=False)
    with pytest.raises(RateLimited):
        await call(router, sync=True, cache_enabled=False)
    assert len(router.requests) == 1
