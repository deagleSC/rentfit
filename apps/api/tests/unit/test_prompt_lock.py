"""A prompt's text, user template or output schema cannot change without a VERSION bump."""

import json

from app.llm.prompts import LOCK_FILE, lock_entries


def test_prompts_match_lock_file() -> None:
    with open(LOCK_FILE) as f:
        locked = json.load(f)
    current = lock_entries()
    for pid, entry in current.items():
        assert pid in locked, f"{pid} is new: run `uv run python -m app.llm.prompts`"
        if locked[pid]["version"] == entry["version"]:
            assert locked[pid]["hash"] == entry["hash"], f"{pid} changed without a VERSION bump"
        else:
            raise AssertionError(f"{pid} VERSION changed: run `uv run python -m app.llm.prompts`")
    assert set(locked) == set(current), "lock file lists prompts that no longer exist"
