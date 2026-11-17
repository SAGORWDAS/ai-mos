"""Repeatable labelled reply evaluation; synthetic fixtures never certify live accuracy."""

import argparse
import json
from collections import Counter
from pathlib import Path

from app.growth.knowledge import classify


def evaluate(examples, predictions=None):
    if not examples or len({row["id"] for row in examples}) != len(examples):
        raise ValueError("Dataset must be nonempty with unique IDs")
    predicted = (
        {row["id"]: row["label"] for row in predictions} if predictions is not None else None
    )
    if predictions is not None and (
        len(predicted) != len(predictions) or set(predicted) != {r["id"] for r in examples}
    ):
        raise ValueError("Predictions must contain exactly one result per dataset ID")
    confusion = Counter()
    failures = []
    abstentions = 0
    for row in examples:
        actual = predicted[row["id"]] if predicted is not None else classify(row["text"])["label"]
        confusion[(row["label"], actual)] += 1
        abstentions += actual == "needs_human"
        if actual != row["label"]:
            failures.append({"id": row["id"], "expected": row["label"], "actual": actual})
    labels = sorted({label for pair in confusion for label in pair})
    metrics = {}
    for label in labels:
        tp = confusion[(label, label)]
        precision = (
            tp / sum(v for (expected, actual), v in confusion.items() if actual == label)
            if any(actual == label for expected, actual in confusion)
            else None
        )
        recall = (
            tp / sum(v for (expected, actual), v in confusion.items() if expected == label)
            if any(expected == label for expected, actual in confusion)
            else None
        )
        metrics[label] = {"precision": precision, "recall": recall}
    return {
        "examples": len(examples),
        "accuracy": 1 - len(failures) / len(examples),
        "abstention_rate": abstentions / len(examples),
        "by_label": metrics,
        "failures": failures,
        "provenance": dict(Counter(row.get("source", "unspecified") for row in examples)),
        "note": "Synthetic results measure regression behavior only. Use independent labels "
        "on representative examples and real model predictions for promotion decisions.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--minimum-accuracy", type=float, default=0.85)
    args = parser.parse_args()

    def read(path):
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    report = evaluate(read(args.dataset), read(args.predictions) if args.predictions else None)
    serialized = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    raise SystemExit(0 if report["accuracy"] >= args.minimum_accuracy else 1)


if __name__ == "__main__":
    main()
