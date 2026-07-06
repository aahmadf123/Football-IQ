"""Metric schema coverage for workload-fusion scalar fields (Issue #149)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.models import Metric
from app.routers.metrics import (
    REVIEW_CANDIDATE_METRIC_NAMES,
    MetricCreate,
    MetricResponse,
)


def test_metric_create_accepts_workload_fields() -> None:
    payload = MetricCreate(
        clip_id=uuid.uuid4(),
        tracklet_id=uuid.uuid4(),
        metric_name="workload_fusion",
        metric_value={"attribution": "player"},
        sprint_count=4,
        asymmetry_index=1.28,
        injury_risk_score=0.45,
    )

    assert payload.sprint_count == 4
    assert payload.asymmetry_index == 1.28
    assert payload.injury_risk_score == 0.45


def test_workload_fusion_is_always_experimental() -> None:
    # The create endpoint forces experimental_flag for review-candidate names —
    # workload_fusion must be in that set so risk signals can never be
    # pre-marked analytics_safe by a caller.
    assert "workload_fusion" in REVIEW_CANDIDATE_METRIC_NAMES


def test_metric_response_serializes_workload_fields() -> None:
    metric = MagicMock(spec=Metric)
    metric.id = uuid.uuid4()
    metric.clip_id = uuid.uuid4()
    metric.tracklet_id = uuid.uuid4()
    metric.metric_name = "workload_fusion"
    metric.metric_value = {"attribution": "player"}
    metric.unit = "review"
    metric.is_suppressed = False
    metric.suppression_reason = None
    metric.experimental_flag = True
    metric.analytics_safe = False
    metric.confidence = 0.82
    metric.effort_zscore = None
    metric.loaf_flag = None
    metric.sprint_count = 4
    metric.asymmetry_index = 1.28
    metric.injury_risk_score = 0.45
    metric.evidence_uri = None
    metric.model_version_id = None
    metric.calibration_version_id = None
    metric.job_id = None
    metric.created_at = datetime(2026, 7, 1, tzinfo=UTC)

    response = MetricResponse.from_orm_metric(metric)

    assert response.sprint_count == 4
    assert response.asymmetry_index == 1.28
    assert response.injury_risk_score == 0.45
