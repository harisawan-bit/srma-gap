"""Offline unit tests for the pure verdict() function.

These exercise every branch of the evidence-gap heuristic without touching the
network (verdict() only does arithmetic on its three integer arguments).
"""

from srma_gap import verdict


def test_weak_pool():
    # pool < 20 -> WEAK POOL takes priority over everything else
    assert verdict(prior_ma=0, registrations=0, pool=10).startswith("WEAK POOL")


def test_saturated():
    # ma >= 100 AND reg >= 100 -> SATURATED
    assert verdict(prior_ma=150, registrations=200, pool=500).startswith("SATURATED")


def test_ma_saturated_registry_quiet():
    # ma >= 100 AND reg < 100 -> MA-SATURATED, registry quiet
    out = verdict(prior_ma=150, registrations=50, pool=500)
    assert out.startswith("MA-SATURATED")


def test_real_gap():
    # ma < 100 AND pool >= 50 -> REAL GAP
    assert verdict(prior_ma=50, registrations=50, pool=100).startswith("REAL GAP")


def test_possible_gap():
    # default fallthrough: ma < 100, pool not large enough
    assert verdict(prior_ma=50, registrations=50, pool=30).startswith("POSSIBLE GAP")
