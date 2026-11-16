"""Daily cap and request-path RPM bucket (Phase 2 exit check: the budget blocks calls at the limit)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.llm import budget
from app.llm.errors import BudgetExhausted, RateLimited

DAY = date(2030, 1, 1)


async def test_budget_blocks_at_the_cap(db):
    for expected in (1, 2, 3):
        assert await budget.reserve(3, day=DAY) == expected
    with pytest.raises(BudgetExhausted):
        await budget.reserve(3, day=DAY)
    assert await budget.used_today(day=DAY) == 3


async def test_zero_cap_blocks_the_first_call(db):
    with pytest.raises(BudgetExhausted):
        await budget.reserve(0, day=DAY)


async def test_budget_resets_each_utc_day(db):
    await budget.reserve(1, day=DAY)
    with pytest.raises(BudgetExhausted):
        await budget.reserve(1, day=DAY)
    assert await budget.reserve(1, day=date(2030, 1, 2)) == 1


async def test_per_model_rows_do_not_count_against_the_cap(db):
    await budget.record_model("b:free", day=DAY)
    await budget.record_model("b:free", day=DAY)
    assert await budget.reserve(1, day=DAY) == 1


async def test_rpm_bucket_limits_each_minute(db):
    t = datetime(2030, 1, 1, 12, 0, 15, tzinfo=UTC)
    await budget.throttle(2, now=t)
    await budget.throttle(2, now=t)
    with pytest.raises(RateLimited) as exc:
        await budget.throttle(2, now=t)
    assert 40 <= exc.value.retry_after <= 45  # until the next minute
    await budget.throttle(2, now=t.replace(minute=1))  # new minute, new bucket
