from __future__ import annotations

from typing import Iterable


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def safe_float(value: float | int | None, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def trapezoid_score(x: float, a: float, b: float, c: float, d: float) -> float:
    """
    Piecewise trapezoid score in [0, 100].
    a <= b <= c <= d
    """
    if a > b or b > c or c > d:
        raise ValueError("Invalid trapezoid parameters: must satisfy a <= b <= c <= d")

    if x <= a or x >= d:
        return 0.0
    if b <= x <= c:
        return 100.0
    if a < x < b:
        if b == a:
            return 100.0
        return 100.0 * (x - a) / (b - a)
    if c < x < d:
        if d == c:
            return 100.0
        return 100.0 * (d - x) / (d - c)
    return 0.0


def inverse_trapezoid_score(x: float, a: float, b: float, c: float, d: float) -> float:
    """
    Good when x is small, bad when x is large.
    a <= b <= c <= d
    """
    if a > b or b > c or c > d:
        raise ValueError("Invalid inverse trapezoid parameters: must satisfy a <= b <= c <= d")

    if x <= b:
        return 100.0
    if x >= d:
        return 0.0
    if c <= x < d:
        if d == c:
            return 0.0
        return 100.0 * (d - x) / (d - c)
    if b < x < c:
        return 100.0
    return 100.0


def weighted_sum(items: Iterable[tuple[float, float]]) -> float:
    total = 0.0
    for weight, value in items:
        total += weight * value
    return clamp(total)
