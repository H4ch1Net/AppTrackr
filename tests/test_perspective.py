"""'In other terms' comparisons: readable picks, honest labels."""

from apptrackr import perspective as pv
from apptrackr.paths import assets_dir


def _stick(key: str) -> pv.Yardstick:
    return next(s for s in pv.YARDSTICKS if s.key == key)


def test_counts_and_percentages():
    everest = _stick("everest")
    assert pv.describe(28 * 60, everest).value == "2"
    assert pv.describe(28 * 60, everest).label == "Everest summit days"
    assert pv.describe(14 * 60, everest).label == "Everest summit day"  # singular at exactly one
    half = pv.describe(7 * 60, everest)
    assert half.value == "50%" and half.label.startswith("of an Everest")
    assert pv.describe(14 * 60 * 2.4, everest).value == "2.4"
    assert pv.describe(14 * 60 * 1234, everest).value == "1,234"


def test_special_phrasings():
    assert pv.describe(5, _stick("walk")).value == "417 m"  # short walks read in metres
    assert pv.describe(600 * 60 * 2.5, _stick("language")).value == "2.5×"


def test_pick_is_varied_and_readable():
    for minutes in (5, 90, 283, 3000, 36000, 300000):
        facts = pv.pick(minutes, 3)
        assert 1 <= len(facts) <= 3
        assert len({f.key for f in facts}) == len(facts)
        for f in facts:
            assert 0.02 <= f.ratio <= _stick(f.key).max_count
    assert pv.pick(0, 3) == []


def test_shuffle_rotates():
    first = [f.key for f in pv.pick(3000, 3, offset=0)]
    second = [f.key for f in pv.pick(3000, 3, offset=1)]
    assert first != second


def test_every_yardstick_has_an_icon():
    for stick in pv.YARDSTICKS:
        assert (assets_dir() / "icons" / f"{stick.icon}.svg").exists(), stick.icon
        assert stick.basis and stick.many and stick.part
