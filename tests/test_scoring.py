from research_x.adapters.synthetic import SyntheticAdapter
from research_x.contracts import AcquisitionTarget, AdapterConfig, PromotionStatus, TargetKind
from research_x.scoring import score_adapters


def test_scoring_promotes_strong_adapter() -> None:
    adapter = SyntheticAdapter(AdapterConfig(adapter_id="synthetic"))
    outcomes = [adapter.fetch(AcquisitionTarget(TargetKind.SEARCH, "x", limit=3))]

    metrics = score_adapters(
        outcomes,
        expected_targets=1,
        thresholds={
            "min_score": 0.5,
            "min_success_rate": 1.0,
            "min_items": 3,
            "max_error_rate": 0.0,
        },
    )

    assert metrics["synthetic"].promotion_status == PromotionStatus.PROMOTED
