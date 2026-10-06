"""'In other terms' comparisons: whole counts only, readable picks, honest labels."""

from apptrackr import perspective as pv
from apptrackr.paths import assets_dir

UNIT = pv.Yardstick("unit", 1, "things", "One minute each", "clock", "test", max_count=1e9, one="thing")


def _stick(key: str) -> pv.Yardstick:
    return next(s for s in pv.YARDSTICKS if s.key == key)


def _totals(low: float = 1, high: float = 20_000 * 60, step: float = 1.13):
    """Totals in minutes from *low* to *high*, spaced evenly on a log scale."""
    minutes = low
    while minutes <= high:
        yield minutes
        minutes *= step
    yield high


def _keys(minutes: float, offset: int = 0) -> set[str]:
    return {f.key for f in pv.pick(minutes, 6, offset)}


def test_number_formatting():
    def value(ratio: float) -> str:
        return pv.describe(ratio, UNIT).value

    assert value(1) == "1"
    assert value(2) == "2"  # a trailing .0 is dropped
    assert value(2.4) == "2.4"
    assert value(9.94) == "9.9"
    assert value(9.96) == "10"
    assert value(12.4) == "12"
    assert value(1234) == "1,234"
    assert value(999_999) == "999,999"
    assert value(999_999.6) == "1 million"
    assert value(1_234_567) == "1.2 million"
    assert value(12_345_678) == "12 million"


def test_singular_when_the_count_reads_one():
    everest = _stick("everest")
    assert (pv.describe(14 * 60, everest).value, pv.describe(14 * 60, everest).label) == ("1", "Everest summit day")
    assert pv.describe(14 * 60 * 1.04, everest).label == "Everest summit day"  # still reads "1"
    assert pv.describe(14 * 60 * 1.06, everest).label == "Everest summit days"  # reads "1.1"
    assert pv.describe(28 * 60, everest).label == "Everest summit days"
    assert pv.describe(600 * 60, _stick("language")).label == "French course"
    assert pv.describe(10_000 * 60, _stick("mastery")).label == "path to mastery"
    assert pv.describe(1_000_000, UNIT).label == "things"  # "1 million things"
    walk = pv.describe(12, _stick("walk"))
    assert (walk.value, walk.label) == ("1", "km walked")  # units read the same either way


def test_walking_reads_in_metres_then_km():
    metres = pv.describe(5, _stick("metres"))
    assert (metres.value, metres.label) == ("417", "m walked")
    for minutes in _totals():
        ranked = {s.key for s in pv._ranked(minutes)}
        assert ranked & {"metres", "walk"}, minutes
        assert not {"metres", "walk"} <= ranked, minutes  # never both at once


def test_no_percentages_only_counts():
    for minutes in _totals():
        for offset in range(3):
            for fact in pv.pick(minutes, 6, offset):
                assert "%" not in fact.value + fact.label + fact.basis, (minutes, fact)
                assert fact.ratio >= 1, (minutes, fact)
                number = fact.value.removesuffix(" million").replace(",", "")
                assert float(number) >= 1, (minutes, fact)


def test_every_total_has_six_readable_picks():
    for minutes in _totals(high=100_000 * 60):
        assert pv.readable_count(minutes) >= 6, minutes
        for offset in range(3):
            facts = pv.pick(minutes, 6, offset)
            assert len(facts) == 6, (minutes, offset)
            assert len({f.key for f in facts}) == 6, (minutes, offset)
    assert pv.pick(0, 6) == [] and pv.pick(-5, 6) == []


def test_first_picks_read_well_and_vary():
    for minutes in (30, 90, 283, 3000, 36000, 600000):
        facts = pv.pick(minutes, 6)
        assert all(f.ratio < 100 for f in facts), minutes
        assert sum(2 <= f.ratio <= 30 for f in facts) >= 4, minutes
        sticks = [_stick(f.key) for f in facts]
        assert len({s.group for s in sticks}) >= 4, minutes
        assert len({s.icon for s in sticks}) == 6, minutes


def test_big_counts_wait_for_shuffle():
    for minutes in (30, 283, 3000):
        assert "heartbeats" not in _keys(minutes), minutes
        assert any("heartbeats" in _keys(minutes, k) for k in range(1, 20)), minutes


def test_shuffle_rotates():
    for minutes in (1, 5, 30, 3000, 600000):
        sets = [_keys(minutes, k) for k in range(5)]
        assert all(a != b for a, b in zip(sets, sets[1:], strict=False)), minutes  # every press brings something new
    assert pv.pick(3000, 6, 4) == pv.pick(3000, 6, 4)  # deterministic
    seen: set[str] = set()
    for k in range(pv.readable_count(3000)):
        seen |= _keys(3000, k)
    assert len(seen) == pv.readable_count(3000)  # keep pressing and everything turns up


def test_yardsticks_span_seconds_to_thousands_of_hours():
    assert len(pv.YARDSTICKS) >= 35
    assert len({s.key for s in pv.YARDSTICKS}) == len(pv.YARDSTICKS)
    assert min(s.minutes for s in pv.YARDSTICKS) < 1
    assert max(s.minutes for s in pv.YARDSTICKS) >= 1000 * 60
    assert len({s.group for s in pv.YARDSTICKS}) >= 6


def test_every_yardstick_has_an_icon_and_a_basis():
    for stick in pv.YARDSTICKS:
        assert (assets_dir() / "icons" / f"{stick.icon}.svg").exists(), stick.icon
        assert stick.many and stick.basis
        assert "—" not in stick.many + stick.one + stick.basis  # no em dashes
