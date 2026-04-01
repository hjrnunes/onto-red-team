import json
import logging
import random
from pathlib import Path

import yaml

from refiner.models import (
    AxisEnumeration,
    DomainContextAxis,
    DomainContextProfile,
    Policy,
    SampledAxis,
)

logger = logging.getLogger(__name__)

RELEVANCE_WEIGHTS = {"high": 3, "medium": 2, "low": 1}


def relevance_weights(enumerations: list[AxisEnumeration]) -> list[float]:
    raw = [RELEVANCE_WEIGHTS[e.relevance] for e in enumerations]
    total = sum(raw)
    return [w / total for w in raw]


def sample_axes(
    profile: DomainContextProfile,
    n: int,
) -> list[list[SampledAxis]]:
    # Filter to axes with enumerations
    usable_axes = [a for a in profile.axes if a.enumerations]
    if not usable_axes:
        return []

    weights_per_axis = [relevance_weights(a.enumerations) for a in usable_axes]

    seen: set[tuple[str, ...]] = set()
    results: list[list[SampledAxis]] = []

    for _ in range(n * 3):  # oversample to account for dedup
        sample = []
        for axis, weights in zip(usable_axes, weights_per_axis):
            chosen = random.choices(axis.enumerations, weights=weights, k=1)[0]
            sample.append(SampledAxis(
                cco_class_uri=axis.cco_class_uri,
                cco_class_label=axis.cco_class_label,
                role=axis.role,
                sampled_uri=chosen.class_uri,
                sampled_label=chosen.class_label,
                source_ontology=chosen.source_ontology,
                relevance=chosen.relevance,
            ))

        key = tuple(sa.sampled_uri for sa in sample)
        if key not in seen:
            seen.add(key)
            results.append(sample)
            if len(results) >= n:
                break

    return results
