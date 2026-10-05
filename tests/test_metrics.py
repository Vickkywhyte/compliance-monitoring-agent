"""Unit tests for all 15 evaluation metrics (Phase 7).

All tests use fixture inputs from tests/fixtures/metrics/cases.json.
No LLM calls are made.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CASES_PATH = Path(__file__).parent / "fixtures" / "metrics" / "cases.json"


@pytest.fixture(scope="module")
def cases() -> dict:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Detection metrics
# ---------------------------------------------------------------------------

def test_detection_recall_detected(cases):
    from compliance_agent.evaluation.metrics.coverage import DetectionRecall
    m = DetectionRecall()
    score = m.compute(cases["detection_recall"]["golden"], cases["detection_recall"]["actual_detected"])
    assert score == 1.0


def test_detection_recall_missed(cases):
    from compliance_agent.evaluation.metrics.coverage import DetectionRecall
    m = DetectionRecall()
    score = m.compute(cases["detection_recall"]["golden"], cases["detection_recall"]["actual_missed"])
    assert score == 0.0


def test_detection_precision_batch(cases):
    from compliance_agent.evaluation.metrics.coverage import DetectionPrecision
    m = DetectionPrecision()
    # 2 TP, 1 FP → precision = 2/3
    score = m.compute_batch(
        cases["detection_precision"]["golden_list"],
        cases["detection_precision"]["actual_list"],
    )
    assert abs(score - 2 / 3) < 1e-9


# ---------------------------------------------------------------------------
# Mapping metrics
# ---------------------------------------------------------------------------

def test_mapping_precision_all_correct(cases):
    from compliance_agent.evaluation.metrics.mapping import MappingPrecision
    m = MappingPrecision()
    score = m.compute(cases["mapping_precision"]["golden"], cases["mapping_precision"]["actual_two_correct"])
    assert score == 1.0


def test_mapping_precision_partial(cases):
    from compliance_agent.evaluation.metrics.mapping import MappingPrecision
    m = MappingPrecision()
    score = m.compute(cases["mapping_precision"]["golden"], cases["mapping_precision"]["actual_one_wrong"])
    assert score == 0.5


def test_mapping_recall_all(cases):
    from compliance_agent.evaluation.metrics.mapping import MappingRecall
    m = MappingRecall()
    score = m.compute(cases["mapping_recall"]["golden"], cases["mapping_recall"]["actual_all"])
    assert score == 1.0


def test_mapping_recall_partial(cases):
    from compliance_agent.evaluation.metrics.mapping import MappingRecall
    m = MappingRecall()
    score = m.compute(cases["mapping_recall"]["golden"], cases["mapping_recall"]["actual_partial"])
    assert score == 0.5


def test_confidence_brier_perfect(cases):
    from compliance_agent.evaluation.metrics.mapping import ConfidenceBrier
    m = ConfidenceBrier()
    score = m.compute(cases["confidence_brier"]["golden"], cases["confidence_brier"]["actual_perfect"])
    assert score == pytest.approx(0.0)


def test_confidence_brier_wrong(cases):
    from compliance_agent.evaluation.metrics.mapping import ConfidenceBrier
    m = ConfidenceBrier()
    score = m.compute(cases["confidence_brier"]["golden"], cases["confidence_brier"]["actual_wrong"])
    assert score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Proposal metrics
# ---------------------------------------------------------------------------

def test_proposal_acceptance_rate(cases):
    from compliance_agent.evaluation.metrics.proposal import ProposalAcceptanceRate
    m = ProposalAcceptanceRate()
    assert m.compute(cases["proposal_rates"]["golden"], cases["proposal_rates"]["actual_approve"]) == 1.0
    assert m.compute(cases["proposal_rates"]["golden"], cases["proposal_rates"]["actual_edit"]) == 0.0


def test_proposal_edit_rate(cases):
    from compliance_agent.evaluation.metrics.proposal import ProposalEditRate
    m = ProposalEditRate()
    assert m.compute(cases["proposal_rates"]["golden"], cases["proposal_rates"]["actual_edit"]) == 1.0
    assert m.compute(cases["proposal_rates"]["golden"], cases["proposal_rates"]["actual_approve"]) == 0.0


def test_proposal_rejection_rate(cases):
    from compliance_agent.evaluation.metrics.proposal import ProposalRejectionRate
    m = ProposalRejectionRate()
    assert m.compute(cases["proposal_rates"]["golden"], cases["proposal_rates"]["actual_reject"]) == 1.0
    assert m.compute(cases["proposal_rates"]["golden"], cases["proposal_rates"]["actual_approve"]) == 0.0


# ---------------------------------------------------------------------------
# Routing metrics
# ---------------------------------------------------------------------------

def test_routing_accuracy_correct(cases):
    from compliance_agent.evaluation.metrics.routing import RoutingAccuracy
    m = RoutingAccuracy()
    assert m.compute(cases["routing_accuracy"]["golden"], cases["routing_accuracy"]["actual_correct"]) == 1.0
    assert m.compute(cases["routing_accuracy"]["golden"], cases["routing_accuracy"]["actual_wrong"]) == 0.0


def test_severity_accuracy(cases):
    from compliance_agent.evaluation.metrics.routing import SeverityAccuracy
    m = SeverityAccuracy()
    assert m.compute(cases["severity_accuracy"]["golden"], cases["severity_accuracy"]["actual_correct"]) == 1.0
    assert m.compute(cases["severity_accuracy"]["golden"], cases["severity_accuracy"]["actual_wrong"]) == 0.0


# ---------------------------------------------------------------------------
# Summary metrics (fixture mode — no LLM)
# ---------------------------------------------------------------------------

def test_summary_faithfulness(cases):
    from compliance_agent.evaluation.metrics.summary import SummaryFaithfulness
    m = SummaryFaithfulness(judge=None)
    assert m.compute(cases["summary_faithfulness"]["golden"], cases["summary_faithfulness"]["actual_all_yes"]) == pytest.approx(1.0)
    score = m.compute(cases["summary_faithfulness"]["golden"], cases["summary_faithfulness"]["actual_mixed"])
    assert abs(score - 1 / 3) < 1e-9
    assert m.compute(cases["summary_faithfulness"]["golden"], cases["summary_faithfulness"]["actual_empty"]) == 0.0


def test_summary_hallucination_rate(cases):
    from compliance_agent.evaluation.metrics.summary import SummaryHallucinationRate
    m = SummaryHallucinationRate()
    assert m.compute(cases["summary_hallucination"]["golden"], cases["summary_hallucination"]["actual_no_hallucination"]) == pytest.approx(0.0)
    # ["yes", "partial", "no"] → (1 + 0.5) / 3 = 0.5
    score = m.compute(cases["summary_hallucination"]["golden"], cases["summary_hallucination"]["actual_mixed"])
    assert abs(score - 0.5) < 1e-9


def test_summary_rubric_score(cases):
    from compliance_agent.evaluation.metrics.summary import SummaryRubricScore
    m = SummaryRubricScore()
    assert m.compute(cases["summary_rubric"]["golden"], cases["summary_rubric"]["actual_raw_5"]) == pytest.approx(1.0)
    assert m.compute(cases["summary_rubric"]["golden"], cases["summary_rubric"]["actual_raw_3"]) == pytest.approx(0.6)
    assert m.compute(cases["summary_rubric"]["golden"], cases["summary_rubric"]["actual_normalized"]) == pytest.approx(0.8)
