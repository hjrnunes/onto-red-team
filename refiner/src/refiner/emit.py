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
