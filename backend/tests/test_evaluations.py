import json
from pathlib import Path

import pytest

from app.growth.knowledge import classify

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = [
    json.loads(line)
    for line in (ROOT / "evals/data/replies.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda row: row["id"])
def test_supplied_reply_regressions(example):
    assert classify(example["text"])["label"] == example["label"]


def test_ambiguous_reply_requires_human():
    result = classify("Interested, but what is the price and can we schedule a call?")
    assert result["label"] == "needs_human"
    assert result["escalate"] is True
