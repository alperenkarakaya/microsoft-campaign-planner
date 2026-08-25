"""calculate_roi pure-function behavior."""

from types import SimpleNamespace

from routers.campaigns import calculate_roi


def _campaign(**kw):
    base = dict(budget=1000.0, revenue=0.0, views=0, clicks=0, conversions=0,
                roi_percentage=0.0, cpm=0.0, cpc=0.0, cpa=0.0)
    base.update(kw)
    return SimpleNamespace(**base)


def test_full_metrics_compute_all_ratios():
    c = calculate_roi(_campaign(budget=1000.0, revenue=3000.0,
                                views=100_000, clicks=2000, conversions=100))
    assert c.roi_percentage == 200.0          # (3000-1000)/1000*100
    assert c.cpm == 10.0                       # 1000/100000*1000
    assert c.cpc == 0.5                        # 1000/2000
    assert c.cpa == 10.0                       # 1000/100


def test_zeroed_metrics_reset_stale_values():
    # Previously populated, now cleared back to 0 → ratios must reset, not persist.
    c = _campaign(budget=1000.0, revenue=0.0, views=0, clicks=0, conversions=0,
                  cpm=99.0, cpc=99.0, cpa=99.0, roi_percentage=99.0)
    calculate_roi(c)
    assert c.cpm == 0.0 and c.cpc == 0.0 and c.cpa == 0.0
    assert c.roi_percentage == -100.0          # spent budget, no revenue


def test_no_division_by_zero_when_metrics_missing():
    c = calculate_roi(_campaign(budget=500.0, revenue=750.0,
                                views=0, clicks=0, conversions=0))
    assert c.roi_percentage == 50.0
    assert c.cpm == 0.0 and c.cpc == 0.0 and c.cpa == 0.0
