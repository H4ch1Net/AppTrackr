"""Tracked time, retold: "that's 2.4 Everest summit days".

Each yardstick is something people know, with the duration it takes and the
basis for that number, which the UI shows next to the comparison. pick()
chooses yardsticks that land in a readable range for a given total.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

HOUR = 60  # yardsticks are in minutes


@dataclass(frozen=True)
class Yardstick:
    key: str
    minutes: float  # one unit of the yardstick
    many: str  # label after a count: "4.2 Everest summit days"
    part: str  # label after a percentage: "38% of the way to the Moon on Apollo 11"
    basis: str  # where the number comes from, shown under the comparison
    icon: str
    group: str  # used to keep a set of picks varied
    max_count: float = 60  # above this the count stops meaning much
    one: str = ""  # singular label when the count reads exactly 1
    times: bool = False  # counts read as multiples: "2.5×"


YARDSTICKS: tuple[Yardstick, ...] = (
    Yardstick(
        "everest",
        14 * HOUR,
        "Everest summit days",
        "of an Everest summit day",
        "South Col to the summit and back down: about 14 h",
        "mountain",
        "adventure",
        one="Everest summit day",
    ),
    Yardstick(
        "apollo",
        102 * HOUR + 45,
        "trips to the Moon on Apollo 11",
        "of the way to the Moon on Apollo 11",
        "Launch to lunar landing, July 1969: 102 h 45 m",
        "moon",
        "space",
        one="trip to the Moon on Apollo 11",
    ),
    Yardstick(
        "iss",
        92.9,
        "laps of Earth by the ISS",
        "of a lap of Earth by the ISS",
        "The space station circles the planet every 93 minutes",
        "orbit",
        "space",
        max_count=200,
        one="lap of Earth by the ISS",
    ),
    Yardstick(
        "sunlight",
        8 + 19 / 60,
        "trips by sunlight from the Sun to Earth",
        "of sunlight's trip to Earth",
        "Light from the Sun takes 8 min 19 s to reach us",
        "sun",
        "space",
        max_count=400,
        one="trip by sunlight from the Sun to Earth",
    ),
    Yardstick(
        "marathon",
        4 * HOUR + 30,
        "marathons at an everyday pace",
        "of a marathon at an everyday pace",
        "A typical finishing time: about 4 h 30 m",
        "footprints",
        "sport",
        one="marathon at an everyday pace",
    ),
    Yardstick(
        "record",
        2 * HOUR + 35 / 60,
        "world-record marathons",
        "of the marathon world record",
        "Kelvin Kiptum, Chicago 2023: 2:00:35",
        "timer",
        "sport",
        one="world-record marathon",
    ),
    Yardstick(
        "walk",
        12,
        "km walked",
        "of a kilometre on foot",
        "At an easy 5 km/h, without stopping",
        "footprints",
        "everyday",
        max_count=20000,
    ),
    Yardstick(
        "novel",
        90000 / 238,
        "novels read",
        "of a novel",
        "90,000 words at an average 238 words a minute",
        "book",
        "learning",
        one="novel read",
    ),
    Yardstick(
        "flight",
        8 * HOUR,
        "flights from London to New York",
        "of a flight from London to New York",
        "About 8 h in the air",
        "plane",
        "travel",
        one="flight from London to New York",
    ),
    Yardstick(
        "language",
        600 * HOUR,
        "the class hours to learn French or Spanish",
        "of the class hours to learn French or Spanish",
        "The US Foreign Service Institute's estimate: about 600 h",
        "languages",
        "learning",
        max_count=10,
        times=True,
    ),
    Yardstick(
        "mastery",
        10000 * HOUR,
        "the 10,000 hours said to make an expert",
        "of the 10,000 hours said to make an expert",
        "The rule of thumb Malcolm Gladwell made famous",
        "trophy",
        "learning",
        max_count=5,
        times=True,
    ),
    Yardstick(
        "moonwalk",
        384400 * 12,
        "walks to the Moon",
        "of a walk to the Moon",
        "384,400 km at 5 km/h, no breaks",
        "moon",
        "adventure",
        max_count=5,
        one="walk to the Moon",
    ),
    Yardstick(
        "voyager",
        1e6 / (16.9 * 60),
        "million km covered by Voyager 1",
        "covered at Voyager 1's speed",
        "The probe leaves the Sun behind at about 16.9 km/s",
        "rocket",
        "space",
        max_count=2000,
    ),
)


@dataclass(frozen=True)
class Fact:
    key: str
    value: str  # "4.2" or "38%"
    label: str  # "Everest summit days"
    basis: str
    icon: str
    ratio: float


def _count(ratio: float) -> str:
    if ratio < 10:
        text = f"{ratio:.1f}"
        return text[:-2] if text.endswith(".0") else text
    return f"{ratio:,.0f}"


def _percent(ratio: float) -> str:
    pct = ratio * 100
    if pct < 0.1:
        return "<0.1%"
    return f"{pct:.1f}%" if pct < 10 else f"{pct:.0f}%"


def describe(minutes: float, stick: Yardstick) -> Fact:
    """*minutes* of tracked time measured against one yardstick."""
    ratio = minutes / stick.minutes
    if stick.key == "walk" and ratio < 1:
        return Fact(stick.key, f"{ratio * 1000:,.0f} m", "walked", stick.basis, stick.icon, ratio)
    if stick.key == "voyager" and ratio < 1:
        km = ratio * 1e6
        km = round(km, -max(0, len(str(int(km))) - 3))  # three significant figures; the speed is approximate
        return Fact(stick.key, f"{km:,.0f} km", "covered at Voyager 1's speed", stick.basis, stick.icon, ratio)
    if ratio >= 1:
        value = _count(ratio)
        if stick.times:
            return Fact(stick.key, value + "×", stick.many, stick.basis, stick.icon, ratio)
        label = stick.one if value == "1" and stick.one else stick.many
        return Fact(stick.key, value, label, stick.basis, stick.icon, ratio)
    return Fact(stick.key, _percent(ratio), stick.part, stick.basis, stick.icon, ratio)


def _score(minutes: float, stick: Yardstick) -> float | None:
    """Lower reads better. None when the comparison would be too tiny or too large to mean much."""
    ratio = minutes / stick.minutes
    if ratio > stick.max_count or ratio < 0.02:
        return None
    if ratio >= 1:
        return abs(math.log10(ratio) - math.log10(4))  # small whole-ish counts read best
    return abs(math.log10(ratio) - math.log10(0.4)) + 0.35  # "40% of the way" is fun, but counts first


def pick(minutes: float, count: int = 3, offset: int = 0) -> list[Fact]:
    """Up to *count* comparisons for *minutes*, varied across groups.

    *offset* rotates through the readable candidates (the Shuffle button).
    """
    if minutes <= 0:
        return []
    scored = [(s, stick) for stick in YARDSTICKS if (s := _score(minutes, stick)) is not None]
    scored.sort(key=lambda item: (item[0], item[1].key))
    ranked = [stick for _, stick in scored]
    if not ranked:
        return []
    start = (offset * count) % len(ranked)
    ranked = ranked[start:] + ranked[:start]
    chosen: list[Yardstick] = []
    for stick in ranked:  # first pass: one per group
        if len(chosen) < count and all(stick.group != c.group for c in chosen):
            chosen.append(stick)
    for stick in ranked:  # then fill from what is left
        if len(chosen) < count and stick not in chosen:
            chosen.append(stick)
    return [describe(minutes, stick) for stick in chosen]


def readable_count(minutes: float) -> int:
    """How many yardsticks give a readable comparison for *minutes*."""
    return sum(1 for stick in YARDSTICKS if _score(minutes, stick) is not None)
