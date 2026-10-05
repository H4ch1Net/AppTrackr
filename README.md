<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/banner-dark.png">
  <img src="docs/banner-light.png" alt="AppTrackr, foreground time tracker for Windows">
</picture>

Foreground app usage tracker for Windows. Counts the time each app actually has focus,
shows it as a dashboard, calendar and per-app history, and stays out of the way in the tray.

[![CI](https://github.com/H4ch1Net/AppTrackr/actions/workflows/ci.yml/badge.svg)](https://github.com/H4ch1Net/AppTrackr/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/H4ch1Net/AppTrackr?sort=semver)](https://github.com/H4ch1Net/AppTrackr/releases/latest)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078d4)
![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

<img src="docs/screenshots/demo.gif" alt="AppTrackr in motion: dashboard, calendar, apps, rewards and a theme switch" width="900">

</div>

## Overview

Most "screen time" numbers measure how long a window was open. AppTrackr measures how long it was
in front of you: time is credited only to the focused app, stops when you go idle or lock the
screen, and is written to a local SQLite database every 30 seconds. Nothing leaves your machine.

On top of the raw numbers it adds the things you reach for next: a heatmap calendar, per-app
trends and sessions, daily limits with notifications, and an optional rewards layer that turns
time in chosen apps into XP and a small village-building game.

## Features

| Area | What you get |
| --- | --- |
| Tracking | Foreground-only time, idle cut-off at your last input, lock-screen detection, midnight-accurate daily totals, UWP apps resolved to the real app, elevated apps tracked by name |
| Dashboard | Live session dial, today vs. this time yesterday, week total, today by hour, last 14 days, top apps with share and category breakdown |
| In other terms | Today, this week or all time retold as Everest summit days, Apollo 11 trips, ISS laps, marathons, novels and more, each with the basis for its number |
| Calendar | Month heatmap with keyboard navigation, month totals and busiest day, per-day hourly chart and app list |
| Apps | Search, period filter (today to all time), category and favorite filters, sort by time, launches or clicks |
| App detail | Today / 7 / 30 day totals, 30-day chart, recent sessions, first and last seen, longest session, rename, category |
| Control | Per-app daily limits with notifications, per-type notification switches, exclude any app (with undo), pause from the tray for a set time |
| Rewards | Optional XP, levels, streaks and a village-building game whose buildings boost future rewards |
| Desktop | Tray icon with live tooltip, launch at sign-in (starts hidden), single instance, six palettes (three dark, three light) with system switching and 8 accents |
| Motion | Fluent-timed page transitions, odometer readouts, springy switches, check marks that draw in, a gliding fader, hover fades and a tick burst on claims and builds; follows Windows *Animation effects* and can be turned off in Settings |
| Data | CSV and JSON export, consistent database backup and validated restore, automatic schema migrations |
| Updates | Once-a-day check against GitHub releases, in-app download and install |

## Screenshots

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/dashboard.png" alt="Dashboard"><br><sub>Dashboard with the live session, today by hour and top apps</sub></td>
    <td width="50%"><img src="docs/screenshots/calendar.png" alt="Calendar"><br><sub>Calendar heatmap with the selected day's breakdown</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/apps.png" alt="Apps"><br><sub>All apps for a period, filterable and sortable</sub></td>
    <td><img src="docs/screenshots/app-detail.png" alt="App detail"><br><sub>Per-app history, limit, rewards and sessions</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/rewards.png" alt="Rewards"><br><sub>Level progress, pending rewards and earning apps</sub></td>
    <td><img src="docs/screenshots/village.png" alt="Village"><br><sub>Village: buildings, inventory and market</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/dashboard-perspective.png" alt="In other terms"><br><sub>In other terms: the week as Voyager kilometres, marathons and Everest</sub></td>
    <td><img src="docs/screenshots/settings-appearance.png" alt="Appearance settings"><br><sub>Palette gallery, accents and animation switch</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/settings.png" alt="Settings"><br><sub>Check boxes and a ruler slider for idle timeout</sub></td>
    <td><img src="docs/screenshots/dashboard-light.png" alt="Dashboard in the light theme"><br><sub>Paper, the default light palette</sub></td>
  </tr>
</table>

<img src="docs/screenshots/themes.png" alt="All six palettes, each with a different accent" width="100%">

Screenshots and the animation above are generated from demo data with `python scripts/screenshots.py`
and `python scripts/record_demo.py`.

## Design

The interface is styled as an instrument panel: warm neutrals, hairline rules, engraved monospaced labels
and one signal color. Recorded history is drawn in neutral ink; the signal color marks only what is live,
selected or current. Charts use hairline grids, thin bars on tick-mark rulers and a five-step calendar ramp.
Category colors are a categorical palette checked for color-vision-deficiency separation in both modes,
and text never takes a data color. Every palette and accent pair keeps small text at 4.5:1 and marks at
3:1; accents are re-stepped per palette to hold that (`tests/test_theme.py` checks all 48 pairs).

| Element | Choice |
| --- | --- |
| Type | Instrument Sans (interface, tabular figures), Martian Mono (labels) |
| Palettes | Dark: Graphite, Carbon (true black), Midnight. Light: Paper, Porcelain, Sage. System mode switches between your two picks |
| Signal color | Orange `#ff6b1a` by default, 8 presets in Settings |
| Shape | 6 px panels, 4 px controls, 1 px borders, no shadows |

## Installation

Download the latest build from [Releases](https://github.com/H4ch1Net/AppTrackr/releases/latest).

| Package | Use it when |
| --- | --- |
| `AppTrackr_Setup.exe` | You want Start Menu entries, optional sign-in startup and uninstall support. Installs per user, no admin rights needed. |
| `AppTrackr_Portable.zip` | You want to run it from a folder. Extract anywhere and start `AppTrackr.exe`. |

Requirements: Windows 10 or 11 (64-bit).

### Upgrading

Every version keeps your data in `%APPDATA%\AppTrackr`, and installers and portable builds of any
version read the same folder, so upgrading never starts you from zero.

- **From 1.1 or later.** AppTrackr checks GitHub once a day. Choose *Download and install* in Settings;
  the installer replaces the old build and starts the new one, and tracking picks up where it stopped.
- **From 1.0.x.** Run the new `AppTrackr_Setup.exe`. It installs over 1.0 in the same folder, closes the
  running copy and keeps the Start Menu and sign-in entries. To update from inside 1.0 instead, paste
  `https://api.github.com/repos/H4ch1Net/AppTrackr/releases/latest` into *Settings > Updates > Update feed
  URL* (1.0 ships without one) and press *Check for Updates*.
- **Portable.** Extract the new zip anywhere, or over the old folder, and start it. Data stays in `%APPDATA%`.

On the first start after an upgrade that changes the database, AppTrackr copies it to
`data-backup-schema<N>-<date>.sqlite` in the same folder and then upgrades it in a single transaction:
either everything is converted or nothing changes. Upgrading from 1.0 keeps every app, finished session, open
and click count, reward, building and setting, and rebuilds daily totals from the raw sessions, which also
recovers time 1.0 left out (sessions that ended in idle, and sessions that ran past midnight). Sign-in
entries made by 1.0 are updated to start in the tray. If an upgrade ever fails, AppTrackr says so, leaves
the data as it was and points to the backup and the log. `tests/test_upgrade.py` runs this upgrade on a
database written by v1.0.2's own code.

## Usage

AppTrackr starts tracking as soon as it runs. Closing the window keeps it running in the tray;
use **Quit** from the tray menu (or <kbd>Ctrl</kbd>+<kbd>Q</kbd>) to stop it.

- **Pause.** Click the tracking module at the bottom of the sidebar, use the dashboard button, or pick
  *Pause for* in the tray menu to resume automatically after 15 minutes to 2 hours.
- **Daily limits.** Open an app and choose a limit. You get one notification per day when it is passed;
  the dashboard and charts mark the limit.
- **Exclude an app.** Right-click it in any list and choose *Exclude from tracking*. Manage exclusions in
  Settings.
- **Favorites and streaks.** Star apps you want to spend time in. A streak day needs 30 minutes in favorites.
- **Rewards.** Pick earning apps on the Rewards page or from an app's page. Milestones (30 min, 1 h, 2 h, 5 h
  of focus per day) pay XP and resources you spend in the village. Turn the whole layer off in Settings.
- **In other terms.** The dashboard card retells today, this week or all time against known yardsticks.
  *Shuffle* shows others. Each comparison names its basis, for example "South Col to the summit and back
  down: about 14 h".

### Keyboard shortcuts

| Keys | Action |
| --- | --- |
| <kbd>Ctrl</kbd>+<kbd>1</kbd> to <kbd>Ctrl</kbd>+<kbd>5</kbd> | Dashboard, Calendar, Apps, Rewards, Village |
| <kbd>Ctrl</kbd>+<kbd>,</kbd> | Settings |
| <kbd>Ctrl</kbd>+<kbd>F</kbd> | Search apps |
| <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd> | Pause or resume tracking |
| <kbd>Esc</kbd> / <kbd>Alt</kbd>+<kbd>Left</kbd> | Back from an app page |
| <kbd>Left</kbd> <kbd>Right</kbd> <kbd>Up</kbd> <kbd>Down</kbd>, <kbd>PgUp</kbd> <kbd>PgDn</kbd> | Move through days and months in the calendar |
| <kbd>F5</kbd> | Refresh the current page |

### Command line

```text
AppTrackr.exe [--minimized] [--demo] [--data-dir PATH] [--debug] [--version]
```

| Option | Effect |
| --- | --- |
| `--minimized` | Start hidden in the tray (used by the sign-in entry) |
| `--demo` | Use generated sample data in a temporary folder. Nothing real is read or recorded. |
| `--data-dir PATH` | Keep the database and logs in `PATH` |
| `--debug` | Verbose logging |

Starting AppTrackr while it is already running brings the existing window to the front.

### Motion

Animations use Fluent 2 timing (100 to 400 ms, decelerate curves for things that enter, easy-ease for
things that move) and only run in response to a change: a page opens, a filter changes, a value updates
or an item is removed. Background refreshes morph values in place instead of replaying entrances.
AppTrackr follows Windows' *Settings > Accessibility > Visual effects > Animation effects*; the
*Animations* switch under Settings > Appearance overrides it.

## Configuration

All settings live in the app and apply immediately. Storage locations and two environment
variables cover the rest.

| Item | Default |
| --- | --- |
| Database | `%APPDATA%\AppTrackr\data.sqlite` |
| Logs | `%APPDATA%\AppTrackr\logs\apptrackr.log` (rotated, 3 x 1 MB) |
| `APPTRACKR_DATA_DIR` | Overrides the data folder, same as `--data-dir` |
| `APPTRACKR_UPDATE_URL` | Alternative release feed (GitHub releases API URL) |

<details>
<summary>How time is counted</summary>

- The tracker samples the foreground window 4 times per second.
- Focus on the shell (desktop, taskbar, Start, lock screen) and on background helpers is not credited to any app.
- When there has been no input for the idle timeout (5 minutes by default), the session is closed at the
  moment of your last input, so idle time is never counted.
- Locking the screen closes the session the same way.
- Committed time is split at local midnight, so late sessions land on the right days.
- A *launch* is an app going from not running to running. Multi-process apps such as browsers count once.
- Click counting (off by default) stores only a number per app per day.

</details>

## Privacy

- Everything is stored locally in one SQLite file. There is no account, telemetry or cloud sync.
- Window titles, keystrokes and screen contents are never recorded.
- The only network request is the optional daily update check to `api.github.com`.

## Development

Requires Python 3.10 or newer. Tracking only works on Windows, but the UI, tests and demo mode run
anywhere PySide6 does.

```bash
git clone https://github.com/H4ch1Net/AppTrackr.git
cd AppTrackr
python -m venv .venv
.venv\Scripts\activate            # source .venv/bin/activate on Linux/macOS
pip install -e ".[dev]"

python -m apptrackr --demo        # explore with sample data
python -m apptrackr               # real tracking (Windows)
```

| Task | Command |
| --- | --- |
| Tests | `pytest` |
| Lint and format | `ruff check . && ruff format .` |
| Regenerate screenshots | `python scripts/screenshots.py` |
| Record the README animation | `python scripts/record_demo.py` |
| Rebuild the README banner and social preview | `python scripts/make_art.py` |
| Rebuild the app icon | `python scripts/make_icon.py` |
| Build the app folder | `pyinstaller packaging/apptrackr.spec` |
| Build the installer | `iscc /DAppVersion=1.1.0 packaging\installer.iss` |

On headless Linux, Qt needs `libegl1` and `libxkbcommon0`, and tests run with `QT_QPA_PLATFORM=offscreen`
(set automatically by `tests/conftest.py`).

### Releasing

Bump `__version__` in `apptrackr/__init__.py`, write the release page text (including how to update) in
`docs/releases/<version>.md`, then push a matching tag:

```bash
git tag v1.1.0
git push origin v1.1.0
```

`.github/workflows/release-windows.yml` checks that the tag matches the version and that the release notes
exist, runs the tests, builds the PyInstaller bundle, self-tests it, packages the portable zip and the Inno
Setup installer, and publishes both with the notes as the GitHub release. `ci.yml` runs lint and tests on Windows and Linux for every push and pull request.

### Project structure

```text
apptrackr/
  __main__.py        entry point: arguments, logging, single instance, service wiring
  paths.py           data, log and asset locations
  perspective.py     yardsticks for 'In other terms' and how they are picked
  core/              tracker, platform (Win32), launch watcher, click counter, autostart, limits
  data/              SQLite access and migrations, queries, export/backup, app catalog, demo data
  rewards/           milestone rules, reward engine, streaks
  game/              village state and balance values
  updater/           GitHub release check and installer download
  ui/                main window, theme and motion tokens, icons, views and shared widgets
  assets/            logo, Lucide and AppTrackr line icons, illustrations, bundled fonts
packaging/           PyInstaller spec, Inno Setup script, app icon
scripts/             screenshot, demo animation, README art and icon generators
tests/               pytest suite (data, tracker, rewards, updater, offscreen UI)
```

```mermaid
flowchart LR
    P[core.platform<br/>Win32 focus, idle, lock] --> T[core.tracker]
    T -->|30 s checkpoints| DB[(SQLite<br/>data.sqlite)]
    W[core.process_watch<br/>launches] --> DB
    C[core.clicks] --> DB
    DB --> Q[data.queries]
    Q --> UI[ui views]
    DB --> R[rewards.engine] --> G[game.state]
    R --> UI
    G --> UI
    T -->|snapshot| UI
```

<details>
<summary>Troubleshooting</summary>

- **Nothing is tracked.** Check the tracking module at the bottom of the sidebar. *Paused* resumes on click. *Idle* means no
  input for the idle timeout. Apps you excluded are listed in Settings.
- **An app shows up under an odd name.** Open it and use the menu next to *Favorite* to rename it.
- **The window opens at sign-in instead of staying in the tray.** Start AppTrackr once; it updates startup
  entries left by older versions. If that does not help, turn *Launch at startup* off and on in Settings.
- **Something broke.** Run with `--debug` and look at `%APPDATA%\AppTrackr\logs\apptrackr.log`, then
  [open an issue](https://github.com/H4ch1Net/AppTrackr/issues) with the relevant lines.

</details>

## Contributing

Issues and pull requests are welcome. Keep changes focused, run `ruff check .`, `ruff format .` and `pytest`
before pushing, and add a test when you change tracking, data or reward logic. UI changes should come with
regenerated screenshots if they change what the README shows.

## License

[MIT](LICENSE). Icons from [Lucide](https://lucide.dev) (ISC, see `apptrackr/assets/icons/LICENSE`), plus a few
drawn for AppTrackr (marked in the SVG).
Fonts: [Instrument Sans](https://github.com/Instrument/instrument-sans) and
[Martian Mono](https://github.com/evilmartians/mono), both SIL Open Font License 1.1
(see `apptrackr/assets/fonts`).
