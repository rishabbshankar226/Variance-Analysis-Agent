"""One explicit flat segment dimension; labels never imply a hierarchy."""
from __future__ import annotations

from .audience import AudienceConfig
from .limits import validate_text
from .models import AnalysisConfig

SEGMENT_KEYS = ("segment", "division", "region", "geography", "business_unit")


def read_segment(row: dict[str, object], config: AnalysisConfig) -> tuple[str, bool]:
    if not isinstance(config, AudienceConfig) or not config.extended_headers:
        return "", False
    if any(key in row for key in ("parent_segment", "subsegment", "sub_segment", "segment_level_2")):
        raise ValueError("Only one flat segment is supported; remove the parent or nested segment dimension.")
    keys = [key for key in SEGMENT_KEYS if key in row]
    if len(keys) > 1:
        raise ValueError("More than one segment column found; map one explicitly.")
    if not keys:
        return "", False
    value = row[keys[0]]
    if isinstance(value, (dict, list, tuple, set, bool)):
        raise ValueError("Only a flat segment label is supported; nested segments are not supported.")
    label = "" if value is None else str(value).strip()
    validate_text(label, field="Segment")
    return label, True
