def score(lead):
    """Versioned deterministic qualification rubric, independent of model output."""
    return min(
        100,
        (25 if lead.company else 0)
        + (20 if lead.domain else 0)
        + lead.source_confidence // 4
        + (30 if lead.lawful_basis != "not_established" else 0),
    )
