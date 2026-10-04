"""Change detection layer: stable IDs, diffs, and Change record emission."""
from compliance_agent.detection.detector import DetectReport, detect
from compliance_agent.detection.stable_id import extract_stable_id

__all__ = ["DetectReport", "detect", "extract_stable_id"]
