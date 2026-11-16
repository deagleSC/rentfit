"""LLM_PROVIDER=fake (dev, tests): deterministic output, no network, no budget, no DB."""

from app.llm.prompts import load_all
from app.llm.prompts.smoke import ExtractInput, ExtractOutput, ReplyInput
from app.llm.wrapper import call_structured, deadline_in, stream_text

load_all()


async def test_fake_structured_call() -> None:
    res = await call_structured("structured", "smoke_extract", ExtractInput(description="x"), deadline=deadline_in(5))
    assert isinstance(res.value, ExtractOutput) and res.value.bhk == 2 and res.model_id == "fake"


async def test_fake_stream() -> None:
    out = [t async for t in stream_text("chat", "smoke_reply", ReplyInput(question="hi"), deadline=deadline_in(5))]
    assert out == ["(fake) hi"]
