"""Supply-glut detection from daily arrivals (plan §6.2).

For one market x commodity:
    baseline = median(arrivals over the previous 28 days, excluding today)
    z        = (arrivals_today - baseline) / MAD
    flag if arrivals_today >= 1.3 x baseline and z >= 2

MAD is the median absolute deviation from the baseline. Requiring both a big
ratio and a big z avoids flagging small moves in steady markets and normal
swings in noisy ones. Thresholds must be tuned by backtest before farmers see
warnings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from math import inf
from statistics import median


@dataclass(frozen=True)
class GlutThresholds:
    ratio: float = 1.3
    z: float = 2.0
    window_days: int = 28
    min_history_days: int = 10


@dataclass(frozen=True)
class GlutSignal:
    market_code: str
    obs_date: date
    arrivals: float | None  # tonnes today
    baseline: float | None  # tonnes, median of the window
    ratio: float | None
    z: float | None
    flagged: bool
    reason: str | None = None  # why no verdict: no_arrivals_today | insufficient_history

    @property
    def pct_above_normal(self) -> float | None:
        return None if self.ratio is None else (self.ratio - 1) * 100


@dataclass(frozen=True)
class RegionalGlut:
    flagged: bool
    spiking: list[str]
    considered: int


def detect_glut(
    market_code: str,
    arrivals_by_day: Mapping[date, float],
    day: date,
    thresholds: GlutThresholds = GlutThresholds(),
) -> GlutSignal:
    today = arrivals_by_day.get(day)
    if today is None:
        return GlutSignal(market_code, day, None, None, None, None, False, "no_arrivals_today")

    start = day - timedelta(days=thresholds.window_days)
    window = [v for d, v in arrivals_by_day.items() if start <= d < day]
    if len(window) < thresholds.min_history_days:
        return GlutSignal(market_code, day, today, None, None, None, False, "insufficient_history")

    baseline = median(window)
    mad = median(abs(v - baseline) for v in window)
    diff = today - baseline
    z = diff / mad if mad > 0 else (inf if diff > 0 else -inf if diff < 0 else 0.0)
    ratio = today / baseline if baseline > 0 else (inf if today > 0 else 1.0)
    flagged = ratio >= thresholds.ratio and z >= thresholds.z
    return GlutSignal(market_code, day, today, baseline, ratio, z, flagged)


def regional_glut(signals: Sequence[GlutSignal], min_markets: int = 2) -> RegionalGlut:
    """A regional glut: at least half of the nearby markets with a verdict spike together."""
    considered = [s for s in signals if s.reason is None]
    spiking = sorted(s.market_code for s in considered if s.flagged)
    flagged = (
        len(considered) >= min_markets and bool(spiking) and 2 * len(spiking) >= len(considered)
    )
    return RegionalGlut(flagged=flagged, spiking=spiking, considered=len(considered))
