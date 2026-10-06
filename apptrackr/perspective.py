"""Tracked time, retold: "that's 2.4 Everest summit days".

Each yardstick is something people know, with the duration it takes and the
basis for that number, which the UI shows next to the comparison. Only counts
are shown (never "38% of a ..."), so a yardstick is a candidate only
once the total covers at least one of it. pick() chooses yardsticks that land
in a readable range for a given total.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SECOND = 1 / 60
HOUR = 60  # yardsticks are in minutes
DAY = 24 * HOUR

BEST = (2, 30)  # counts in this range read best
SWEET = math.sqrt(BEST[0] * BEST[1])  # about 7.7, the middle of that range on a log scale
VARIETY = 4  # places in line a pick gives up for each repeat of its group (twice that for its icon)


@dataclass(frozen=True)
class Yardstick:
    key: str
    minutes: float  # one unit of the yardstick
    many: str  # label after a count: "4.2 Everest summit days"
    basis: str  # where the number comes from, shown under the comparison
    icon: str
    group: str  # used to keep a set of picks varied
    max_count: float = 100_000  # from here on the count stops meaning much
    one: str = ""  # singular label when the count reads exactly 1; defaults to *many*


YARDSTICKS: tuple[Yardstick, ...] = (
    # Everyday
    Yardstick(
        "typing",
        1.5 * SECOND,
        "words typed",
        "At an average 40 words a minute",
        "keyboard",
        "everyday",
        max_count=10_000_000,
        one="word typed",
    ),
    Yardstick(
        "handwash",
        20 * SECOND,
        "hand washes",
        "The 20 s scrub health services advise",
        "droplet",
        "everyday",
        one="hand wash",
    ),
    Yardstick(
        "song",
        3.5,
        "pop songs",
        "An average hit runs about 3.5 min",
        "music",
        "everyday",
        one="pop song",
    ),
    Yardstick(
        "commute",
        27,
        "commutes to work",
        "The average US one-way trip: about 27 min",
        "car",
        "everyday",
        one="commute to work",
    ),
    Yardstick(
        "workday",
        8 * HOUR,
        "working days",
        "A standard 8-hour day",
        "briefcase",
        "everyday",
        one="working day",
    ),
    Yardstick(
        "workweek",
        40 * HOUR,
        "work weeks",
        "Five 8-hour days",
        "calendar-days",
        "everyday",
        one="work week",
    ),
    Yardstick(
        "workyear",
        46 * 40 * HOUR,
        "working years",
        "46 weeks of 40 h, after holidays",
        "briefcase",
        "everyday",
        one="working year",
    ),
    # Food
    Yardstick(
        "espresso",
        27.5 * SECOND,
        "espresso shots",
        "Pulled in about 25 to 30 s",
        "cup",
        "food",
        one="espresso shot",
    ),
    Yardstick(
        "pizza",
        1.5,
        "Neapolitan pizzas baked",
        "About 90 s in a wood-fired oven",
        "flame",
        "food",
        one="Neapolitan pizza baked",
    ),
    Yardstick(
        "noodles",
        3,
        "cups of instant noodles",
        "The classic 3-minute wait",
        "cup",
        "food",
        one="cup of instant noodles",
    ),
    Yardstick(
        "tea",
        4,
        "cups of tea brewed",
        "Black tea steeps for about 4 min",
        "cup",
        "food",
        one="cup of tea brewed",
    ),
    Yardstick(
        "egg",
        6,
        "soft-boiled eggs",
        "About 6 min in boiling water",
        "hourglass",
        "food",
        one="soft-boiled egg",
    ),
    Yardstick(
        "bread",
        40,
        "loaves of bread baked",
        "About 40 min in a hot oven",
        "wheat",
        "food",
        one="loaf of bread baked",
    ),
    # Culture
    Yardstick(
        "trailer",
        2.5,
        "film trailers",
        "Trailers usually run up to 2 min 30 s",
        "play",
        "culture",
        one="film trailer",
    ),
    Yardstick(
        "bohemian",
        5 + 55 / 60,
        "plays of Bohemian Rhapsody",
        "Queen, 1975: 5 min 55 s",
        "music",
        "culture",
        one="play of Bohemian Rhapsody",
    ),
    Yardstick(
        "ted",
        18,
        "TED talks",
        "Talks are capped at 18 min",
        "languages",
        "culture",
        one="TED talk",
    ),
    Yardstick(
        "sitcom",
        22,
        "sitcom episodes",
        "About 22 min without the ads",
        "monitor",
        "culture",
        one="sitcom episode",
    ),
    Yardstick(
        "beethoven",
        70,
        "Beethoven's Ninths",
        "His last symphony runs about 70 min",
        "music",
        "culture",
        one="Beethoven's Ninth",
    ),
    Yardstick(
        "film",
        2 * HOUR,
        "feature films",
        "About 2 h, a typical running time",
        "clapperboard",
        "culture",
        one="feature film",
    ),
    Yardstick(
        "titanic",
        3 * HOUR + 14,
        "screenings of Titanic",
        "James Cameron, 1997: 3 h 14 m",
        "clapperboard",
        "culture",
        one="screening of Titanic",
    ),
    Yardstick(
        "ring",
        15 * HOUR,
        "Ring cycles",
        "Wagner's four operas: about 15 h",
        "castle",
        "culture",
        one="Ring cycle",
    ),
    Yardstick(
        "friends",
        236 * 22,
        "box sets of Friends",
        "All 236 episodes at about 22 min",
        "monitor",
        "culture",
        one="box set of Friends",
    ),
    Yardstick(
        "fogg",
        80 * DAY,
        "trips around the world with Phileas Fogg",
        "Jules Verne's 80 days",
        "globe",
        "culture",
        one="trip around the world with Phileas Fogg",
    ),
    # Sport
    Yardstick(
        "bolt",
        9.58 * SECOND,
        "Usain Bolt 100 m sprints",
        "The world record, Berlin 2009: 9.58 s",
        "zap",
        "sport",
        max_count=10_000_000,
        one="Usain Bolt 100 m sprint",
    ),
    Yardstick(
        "boxing",
        3,
        "boxing rounds",
        "A professional round lasts 3 min",
        "bell",
        "sport",
        one="boxing round",
    ),
    Yardstick(
        "football",
        90,
        "football matches",
        "Two 45-minute halves",
        "ball",
        "sport",
        one="football match",
    ),
    Yardstick(
        "record",
        2 * HOUR + 35 / 60,
        "world-record marathons",
        "Kelvin Kiptum, Chicago 2023: 2:00:35",
        "timer",
        "sport",
        one="world-record marathon",
    ),
    Yardstick(
        "marathon",
        4 * HOUR + 30,
        "marathons at an everyday pace",
        "A typical finishing time: about 4 h 30 m",
        "footprints",
        "sport",
        one="marathon at an everyday pace",
    ),
    Yardstick(
        "tennis",
        11 * HOUR + 5,
        "record tennis matches",
        "Isner v Mahut, Wimbledon 2010: 11 h 5 m",
        "tennis",
        "sport",
        one="record tennis match",
    ),
    Yardstick(
        "lemans",
        24 * HOUR,
        "Le Mans 24-hour races",
        "Cars race nonstop for 24 h",
        "car",
        "sport",
        one="Le Mans 24-hour race",
    ),
    Yardstick(
        "tour",
        80 * HOUR,
        "Tours de France at the winner's pace",
        "Three weeks of racing: about 80 h in the saddle",
        "bike",
        "sport",
        one="Tour de France at the winner's pace",
    ),
    # Travel and adventure
    Yardstick(
        "metres",
        12 / 1000,
        "m walked",
        "At an easy 5 km/h",
        "footprints",
        "travel",
        max_count=1000,  # from there on it reads as km walked
    ),
    Yardstick(
        "walk",
        12,
        "km walked",
        "At an easy 5 km/h, without stopping",
        "footprints",
        "travel",
        max_count=1_000_000,
    ),
    Yardstick(
        "eurostar",
        2 * HOUR + 20,
        "Eurostar trips from London to Paris",
        "St Pancras to Gare du Nord: about 2 h 20 m",
        "train",
        "travel",
        one="Eurostar trip from London to Paris",
    ),
    Yardstick(
        "flight",
        8 * HOUR,
        "flights from London to New York",
        "About 8 h in the air",
        "plane",
        "travel",
        one="flight from London to New York",
    ),
    Yardstick(
        "everest",
        14 * HOUR,
        "Everest summit days",
        "South Col to the summit and back down: about 14 h",
        "mountain",
        "travel",
        one="Everest summit day",
    ),
    Yardstick(
        "drive",
        41 * HOUR,
        "drives from New York to Los Angeles",
        "About 2,800 miles: 41 h at the wheel",
        "car",
        "travel",
        one="drive from New York to Los Angeles",
    ),
    Yardstick(
        "siberia",
        6 * DAY,
        "Trans-Siberian train journeys",
        "Moscow to Vladivostok, 9,289 km: about 6 days",
        "train",
        "travel",
        one="Trans-Siberian train journey",
    ),
    # Space
    Yardstick(
        "lightlap",
        40075 / 299792.458 * SECOND,
        "laps of Earth at light speed",
        "Light could circle the equator 7.5 times a second",
        "globe",
        "space",
        max_count=10_000_000,
        one="lap of Earth at light speed",
    ),
    Yardstick(
        "sunlight",
        8 + 19 / 60,
        "trips by sunlight to Earth",
        "Light from the Sun takes 8 min 19 s to reach us",
        "sun",
        "space",
        one="trip by sunlight to Earth",
    ),
    Yardstick(
        "shuttle",
        8.5,
        "Space Shuttle climbs to orbit",
        "Launch to main engine cutoff: about 8.5 min",
        "rocket",
        "space",
        one="Space Shuttle climb to orbit",
    ),
    Yardstick(
        "iss",
        92.9,
        "laps of Earth by the ISS",
        "The space station circles the planet every 93 min",
        "orbit",
        "space",
        one="lap of Earth by the ISS",
    ),
    Yardstick(
        "mars",
        24 * HOUR + 39 + 35 / 60,
        "days on Mars",
        "A Martian day, or sol: 24 h 40 m",
        "planet",
        "space",
        one="day on Mars",
    ),
    Yardstick(
        "apollo",
        102 * HOUR + 45,
        "trips to the Moon on Apollo 11",
        "Launch to lunar landing, July 1969: 102 h 45 m",
        "moon",
        "space",
        one="trip to the Moon on Apollo 11",
    ),
    Yardstick(
        "voyager",
        1e6 / (16.9 * 60),
        "million km flown by Voyager 1",
        "The probe leaves the Sun behind at about 16.9 km/s",
        "rocket",
        "space",
        max_count=2000,
    ),
    Yardstick(
        "mercury",
        88 * DAY,
        "years on Mercury",
        "Mercury circles the Sun every 88 days",
        "planet",
        "space",
        one="year on Mercury",
    ),
    # Learning
    Yardstick(
        "pages",
        300 / 238,
        "book pages read",
        "About 300 words each at 238 words a minute",
        "scroll",
        "learning",
        one="book page read",
    ),
    Yardstick(
        "lecture",
        50,
        "university lectures",
        "A standard 50-minute class",
        "landmark",
        "learning",
        one="university lecture",
    ),
    Yardstick(
        "novel",
        90000 / 238,
        "novels read",
        "90,000 words at an average 238 words a minute",
        "book",
        "learning",
        one="novel read",
    ),
    Yardstick(
        "driving",
        45 * HOUR,
        "driving courses",
        "UK learners take about 45 h of lessons to pass",
        "steering-wheel",
        "learning",
        one="driving course",
    ),
    Yardstick(
        "language",
        600 * HOUR,
        "French courses",
        "US diplomats' training estimate: about 600 class hours",
        "languages",
        "learning",
        one="French course",
    ),
    Yardstick(
        "mastery",
        10000 * HOUR,
        "paths to mastery",
        "The 10,000-hour rule Malcolm Gladwell made famous",
        "trophy",
        "learning",
        one="path to mastery",
    ),
    # Body
    Yardstick(
        "heartbeats",
        1 / 70,
        "heartbeats",
        "At a resting 70 beats a minute",
        "activity",
        "body",
        max_count=10_000_000,
        one="heartbeat",
    ),
    Yardstick(
        "breaths",
        1 / 15,
        "breaths",
        "About 15 a minute at rest",
        "wind",
        "body",
        max_count=10_000_000,
        one="breath",
    ),
    Yardstick(
        "nap",
        20,
        "power naps",
        "The classic 20-minute nap",
        "moon",
        "body",
        one="power nap",
    ),
    Yardstick(
        "sleep",
        8 * HOUR,
        "nights of sleep",
        "8 h, the middle of the advised 7 to 9",
        "moon",
        "body",
        one="night of sleep",
    ),
)


@dataclass(frozen=True)
class Fact:
    key: str
    value: str  # "4.2", "1,234" or "1.2 million"
    label: str  # "Everest summit days"
    basis: str
    icon: str
    ratio: float


def _number(x: float) -> str:
    if x < 10:
        text = f"{x:.1f}"
        return text[:-2] if text.endswith(".0") else text
    return f"{x:,.0f}"


def _count(ratio: float) -> str:
    """2.4, 12, 1,234, 1.2 million."""
    if round(ratio) >= 1_000_000:
        return _number(ratio / 1_000_000) + " million"
    return _number(ratio)


def describe(minutes: float, stick: Yardstick) -> Fact:
    """*minutes* of tracked time measured against one yardstick."""
    ratio = minutes / stick.minutes
    value = _count(ratio)
    label = stick.one if value == "1" and stick.one else stick.many
    return Fact(stick.key, value, label, stick.basis, stick.icon, ratio)


def _score(minutes: float, stick: Yardstick) -> float | None:
    """Lower reads better. None when the total is under one of the thing, or too many to mean much."""
    ratio = minutes / stick.minutes
    if ratio < 1 or ratio >= stick.max_count:
        return None
    score = 0.5 * abs(math.log10(ratio / SWEET))  # a gentle lean towards the middle of the range
    score += max(0.0, math.log10(BEST[0] / ratio))  # "1.1 Ring cycles" is fine, just less fun
    score += max(0.0, math.log10(ratio / BEST[1]))  # big counts mostly turn up on shuffle
    return score


def _ranked(minutes: float) -> list[Yardstick]:
    scored = [(s, stick) for stick in YARDSTICKS if (s := _score(minutes, stick)) is not None]
    scored.sort(key=lambda item: (item[0], item[1].key))
    return [stick for _, stick in scored]


def pick(minutes: float, count: int = 3, offset: int = 0) -> list[Fact]:
    """Up to *count* comparisons for *minutes*, best first and varied across groups.

    *offset* rotates through the readable candidates (the Shuffle button).
    """
    if minutes <= 0 or count <= 0:
        return []
    ranked = _ranked(minutes)
    if not ranked:
        return []
    # Each press moves on by about *count*; a stride with no factor in common with the number of
    # candidates lets each of them lead a set (leaders are always shown) within that many presses.
    n = len(ranked)
    step = min((s for s in range(1, count + n) if math.gcd(s, n) == 1), key=lambda s: (abs(s - count), -s))
    start = (offset * step) % n
    order = ranked[start:] + ranked[:start]
    # For variety a set may borrow from the next one in line, but never from the one before it
    # (the end of the rotation), so every shuffle brings something new.
    window = order[: max(count, min(count * 2, n - step))]
    chosen: list[Yardstick] = []

    def cost(item: tuple[int, Yardstick]) -> float:
        # Place in line, plus a few places for repeating a group and more for repeating an icon.
        place, stick = item
        repeats = sum(stick.group == c.group for c in chosen)
        return place + VARIETY * repeats + 2 * VARIETY * any(stick.icon == c.icon for c in chosen)

    while len(chosen) < min(count, len(window)):
        chosen.append(min(((i, s) for i, s in enumerate(window) if s not in chosen), key=cost)[1])
    chosen.sort(key=order.index)
    return [describe(minutes, stick) for stick in chosen]


def readable_count(minutes: float) -> int:
    """How many yardsticks give a readable comparison for *minutes*."""
    return sum(1 for stick in YARDSTICKS if _score(minutes, stick) is not None)
