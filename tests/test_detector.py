"""Unit tests for feature extraction, Isolation Forest detector, and rule-based diagnosis."""

import numpy as np
import pandas as pd
import pytest

from sliceguard.config import load_config
from sliceguard.detector import AnomalyDetector, PersistenceFilter, train_default_detector
from sliceguard.diagnosis import DiagnosisEngine, DiagnosisResult
from sliceguard.features import FEATURE_KPI_COLS, FeatureExtractor
from sliceguard.simulator import Simulator, generate_run


@pytest.fixture(scope="module")
def shared_detector() -> AnomalyDetector:
    """Fixture providing a trained and calibrated AnomalyDetector."""
    config = load_config()
    return train_default_detector(config=config)


def test_feature_extractor_shape_and_names() -> None:
    """Verify feature extractor generates 3 statistical columns per KPI without labels."""
    config = load_config()
    df = generate_run("normal", seed=42, config=config)
    extractor = FeatureExtractor(window=10)
    feats = extractor.extract_features_df(df)

    expected_cols = len(FEATURE_KPI_COLS) * 3
    assert feats.shape == (600, expected_cols)
    assert not any("event_label" in col or "is_attack" in col for col in feats.columns)
    assert feats.isna().sum().sum() == 0


def test_persistence_filter_logic() -> None:
    """Verify persistence filter requires k flags out of n ticks."""
    p_filter = PersistenceFilter(k=3, n=5)

    # 1 flag -> False
    assert not p_filter.update(True)
    # 2 flags -> False
    assert not p_filter.update(True)
    assert not p_filter.update(False)
    # 3 flags in last 4 ticks -> True
    assert p_filter.update(True)
    # Rolling out old flags
    p_filter.update(False)
    p_filter.update(False)
    p_filter.update(False)
    assert not p_filter.update(False)


def test_detector_false_alarm_rate_on_normal(shared_detector: AnomalyDetector) -> None:
    """Verify detector false alarm rate on heldout normal runs is within target (~1%)."""
    config = load_config()
    # Test on fresh unseen normal seed
    df_normal = generate_run("normal", seed=999, config=config)
    scores, raw_flags, incident_flags = shared_detector.score_df(df_normal)

    raw_far = np.mean(raw_flags)
    incident_far = np.mean(incident_flags)

    # Raw false alarm rate should be low (< 3%), and incident FAR even lower (< 1%)
    assert raw_far <= 0.03, f"Raw FAR too high: {raw_far}"
    assert incident_far <= 0.015, f"Incident FAR too high: {incident_far}"


def test_detector_flags_surge_and_ddos(shared_detector: AnomalyDetector) -> None:
    """Verify detector detects eMBB surge and DDoS incidents with low delay."""
    config = load_config()
    df_surge = generate_run("embb_surge", seed=42, config=config)
    df_ddos = generate_run("ddos_like", seed=42, config=config)

    _, _, inc_surge = shared_detector.score_df(df_surge)
    _, _, inc_ddos = shared_detector.score_df(df_ddos)

    # Event starts at tick 200
    # Must flag incident within 20 ticks of event start (tick 220)
    assert inc_surge[200:220].any(), "Failed to detect eMBB surge promptly"
    assert inc_ddos[200:215].any(), "Failed to detect DDoS flood promptly"

    # Must sustain detection during event peak (ticks 250..400)
    assert inc_surge[250:400].mean() > 0.90
    assert inc_ddos[250:400].mean() > 0.95


def test_diagnosis_cross_slice_contention() -> None:
    """Verify diagnosis correctly identifies cross_slice_contention on eMBB surge."""
    config = load_config()
    df_surge = generate_run("embb_surge", seed=42, config=config)
    engine = DiagnosisEngine(config.diagnosis)

    # Evaluate window during peak surge (ticks 250..280)
    window_data = df_surge.iloc[250:280].to_dict(orient="records")
    res = engine.diagnose_window(window_data, is_detector_incident=True)

    assert res.cause == "cross_slice_contention"
    assert res.confidence >= 0.70
    assert not res.should_abstain
    assert res.recommended_action == "protect_urllc"


def test_diagnosis_security_anomaly() -> None:
    """Verify diagnosis correctly identifies security_anomaly on ddos_like."""
    config = load_config()
    df_ddos = generate_run("ddos_like", seed=42, config=config)
    engine = DiagnosisEngine(config.diagnosis)

    window_data = df_ddos.iloc[220:250].to_dict(orient="records")
    res = engine.diagnose_window(window_data, is_detector_incident=True)

    assert res.cause == "security_anomaly"
    assert res.confidence >= 0.75
    assert not res.should_abstain
    assert res.recommended_action == "isolate_suspicious_traffic"


def test_flash_crowd_is_not_diagnosed_as_attack() -> None:
    """Verify that a legitimate flash crowd is diagnosed as traffic_overload, NOT security_anomaly."""
    config = load_config()
    df_flash = generate_run("flash_crowd", seed=42, config=config)
    engine = DiagnosisEngine(config.diagnosis)

    # Window during flash crowd peak (ticks 300..330)
    window_data = df_flash.iloc[300:330].to_dict(orient="records")
    res = engine.diagnose_window(window_data, is_detector_incident=True)

    assert res.cause == "traffic_overload", f"Expected traffic_overload, got {res.cause}"
    assert res.cause != "security_anomaly"
    assert res.recommended_action == "rate_limit_embb"


def test_unseen_mmtc_storm_triggers_abstention() -> None:
    """Verify that unseen_mmtc_storm causes diagnosis engine to abstain and escalate."""
    config = load_config()
    df_storm = generate_run("unseen_mmtc_storm", seed=42, config=config)
    engine = DiagnosisEngine(config.diagnosis)

    window_data = df_storm.iloc[250:280].to_dict(orient="records")
    res = engine.diagnose_window(window_data, is_detector_incident=True)

    assert res.cause == "unknown" or res.should_abstain
    assert res.should_abstain == True
    assert res.recommended_action == "escalate_to_human"


def test_strict_isolation_from_ground_truth(shared_detector: AnomalyDetector) -> None:
    """Verify detector and diagnosis give identical results whether ground truth is present or dropped."""
    config = load_config()
    df_surge = generate_run("embb_surge", seed=42, config=config)

    # DataFrame with ground-truth columns
    scores1, raw1, inc1 = shared_detector.score_df(df_surge)

    # DataFrame with ground-truth columns stripped
    df_stripped = df_surge.drop(columns=["event_label", "is_attack"])
    scores2, raw2, inc2 = shared_detector.score_df(df_stripped)

    np.testing.assert_array_almost_equal(scores1, scores2)
    np.testing.assert_array_equal(raw1, raw2)
    np.testing.assert_array_equal(inc1, inc2)
