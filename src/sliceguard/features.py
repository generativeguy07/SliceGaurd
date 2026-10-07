"""Rolling-window feature extraction for telemetry anomaly detection.

Transforms raw observable KPI time-series into statistical feature vectors
(rolling mean, rolling standard deviation, and rate-of-change).
Strictly enforces isolation from ground-truth evaluation labels.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

from sliceguard.simulator import KPIRow, Simulator


FEATURE_KPI_COLS = [
    "embb_demand_pct",
    "embb_served_pct",
    "embb_throughput_mbps",
    "embb_latency_ms",
    "urllc_latency_ms",
    "urllc_loss_pct",
    "urllc_jitter_ms",
    "mmtc_devices",
    "mmtc_reg_failures",
    "cpu_pct",
    "shared_util_pct",
    "req_rate_total",
    "pattern_anomaly_ratio",
]


class FeatureExtractor:
    """Extracts rolling window statistical features for anomaly detection."""

    def __init__(self, window: int = 10) -> None:
        """Initialize extractor with rolling window size (in ticks)."""
        self.window = max(2, window)

    @classmethod
    def get_feature_names(cls) -> List[str]:
        """Return full list of generated feature column names."""
        names = []
        for col in FEATURE_KPI_COLS:
            names.extend([f"{col}_mean", f"{col}_std", f"{col}_diff"])
        return names

    def extract_features_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract rolling features across a full DataFrame of telemetry rows.

        Args:
            df: DataFrame containing at least FEATURE_KPI_COLS.

        Returns:
            DataFrame containing rolling statistical features with index preserved.
        """
        # Strictly ensure no ground-truth column is used
        for col in Simulator.GROUND_TRUTH_COLUMNS:
            if col in df.columns:
                # Do not error, but ensure it is never in feature computation
                pass

        features: Dict[str, pd.Series] = {}

        for col in FEATURE_KPI_COLS:
            if col not in df.columns:
                raise ValueError(f"Required KPI column '{col}' missing from input DataFrame.")

            series = df[col].astype(float)
            # Impute any sporadic NaN from telemetry dropouts with forward/backward fill
            series_clean = series.ffill().bfill().fillna(0.0)

            rolling = series_clean.rolling(window=self.window, min_periods=1)
            features[f"{col}_mean"] = rolling.mean()
            features[f"{col}_std"] = rolling.std().fillna(0.0)
            features[f"{col}_diff"] = series_clean.diff().fillna(0.0)

        feat_df = pd.DataFrame(features, index=df.index)
        return feat_df

    def extract_features_from_history(self, history: List[KPIRow | Dict[str, Any]]) -> pd.DataFrame:
        """Extract features from a list of recent KPIRow history up to the current tick.

        Args:
            history: List of KPIRow instances or dictionary telemetry records.

        Returns:
            DataFrame of features for the latest history rows.
        """
        if not history:
            return pd.DataFrame(columns=self.get_feature_names())

        raw_data = []
        for r in history:
            if hasattr(r, "to_observable_dict"):
                raw_data.append(r.to_observable_dict())
            elif hasattr(r, "items"):
                raw_data.append({k: v for k, v in r.items() if k not in Simulator.GROUND_TRUTH_COLUMNS})
            elif isinstance(r, dict):
                raw_data.append({k: v for k, v in r.items() if k not in Simulator.GROUND_TRUTH_COLUMNS})
            else:
                d = dict(r)
                raw_data.append({k: v for k, v in d.items() if k not in Simulator.GROUND_TRUTH_COLUMNS})

        df = pd.DataFrame(raw_data)
        return self.extract_features_df(df)
