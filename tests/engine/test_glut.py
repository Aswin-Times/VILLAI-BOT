"""Glut detection on daily arrivals (plan §6.2)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.engine.glut import GlutSignal, GlutThresholds, detect_glut, regional_glut

TODAY = date(2026, 11, 19)


def history(values: list[float], today_value: float | None) -> dict[date, float]:
    """`values` fill the days before today, most recent last."""
    h = {TODAY - timedelta(days=len(values) - i): v for i, v in enumerate(values)}
    if today_value is not None:
        h[TODAY] = today_value
    return h


STEADY = [98, 102, 100, 97, 103, 101, 99] * 4  # 28 days around 100 t


def test_flags_a_clear_spike() -> None:
    s = detect_glut("oddanchatram", history(STEADY, 160), TODAY)

    assert s.flagged
    assert s.baseline == pytest.approx(100)
    assert s.ratio == pytest.approx(1.6)
    assert s.pct_above_normal == pytest.approx(60)


def test_small_rise_is_not_a_glut_even_if_statistically_unusual() -> None:
    tight = [100.0] * 14 + [101.0] * 14

    s = detect_glut("m", history(tight, 120), TODAY)

    assert s.z is not None and s.z >= 2
    assert not s.flagged  # 1.2x is below the 1.3x ratio threshold


def test_big_ratio_in_noisy_history_is_not_a_glut() -> None:
    noisy = [50.0, 150.0] * 14  # median 100, MAD 50

    s = detect_glut("m", history(noisy, 140), TODAY)

    assert s.ratio == pytest.approx(1.4)
    assert s.z == pytest.approx(0.8)
    assert not s.flagged


def test_baseline_ignores_today_and_days_outside_the_window() -> None:
    h = history(STEADY, 160)
    h[TODAY - timedelta(days=40)] = 10_000  # too old to count

    assert detect_glut("m", h, TODAY).baseline == pytest.approx(100)


def test_too_little_history_is_never_flagged() -> None:
    s = detect_glut("m", history([100.0] * 5, 500), TODAY)

    assert not s.flagged
    assert s.reason == "insufficient_history"


def test_no_arrivals_reported_today() -> None:
    s = detect_glut("m", history(STEADY, None), TODAY)

    assert not s.flagged
    assert s.reason == "no_arrivals_today"


def test_constant_history_still_flags_a_large_jump() -> None:
    s = detect_glut("m", history([100.0] * 28, 150), TODAY)

    assert s.flagged
    assert s.z == float("inf")


def test_arrivals_after_a_month_of_nothing_count_as_a_glut() -> None:
    s = detect_glut("m", history([0.0] * 28, 5), TODAY)

    assert s.ratio == float("inf")
    assert s.flagged


def test_a_drop_below_a_flat_history_is_not_a_glut() -> None:
    s = detect_glut("m", history([100.0] * 28, 60), TODAY)

    assert s.z == float("-inf")
    assert not s.flagged


def test_thresholds_are_configurable() -> None:
    lenient = GlutThresholds(ratio=1.1, z=1.0)

    assert detect_glut("m", history(STEADY, 120), TODAY, lenient).flagged


def signal(code: str, flagged: bool, reason: str | None = None) -> GlutSignal:
    return GlutSignal(
        market_code=code,
        obs_date=TODAY,
        arrivals=None if reason else 100.0,
        baseline=None if reason else 100.0,
        ratio=None if reason else 1.0,
        z=None if reason else 0.0,
        flagged=flagged,
        reason=reason,
    )


def test_regional_glut_when_half_of_nearby_markets_spike() -> None:
    r = regional_glut([signal("a", True), signal("b", True), signal("c", False)])

    assert r.flagged
    assert r.spiking == ["a", "b"]
    assert r.considered == 3


def test_one_spike_among_three_is_local_only() -> None:
    assert not regional_glut([signal("a", True), signal("b", False), signal("c", False)]).flagged


def test_markets_without_enough_data_do_not_count() -> None:
    r = regional_glut(
        [signal("a", True), signal("b", False), signal("c", False, reason="insufficient_history")]
    )

    assert r.considered == 2
    assert r.flagged


def test_a_single_market_is_never_a_regional_glut() -> None:
    assert not regional_glut([signal("a", True)]).flagged
