# AppTrackr

A Windows desktop app that tracks which applications you actually use, and for how long. Time is counted only while an app has focus, so the numbers reflect reality rather than just "was it open."

## Screenshots

### Dashboard
<img width="1073" height="737" alt="Dashboard" src="https://github.com/user-attachments/assets/9321c718-12b5-4900-bf14-4b7efd1281f4" />

### Calendar
<img width="1078" height="744" alt="Calendar" src="https://github.com/user-attachments/assets/0051ab63-14c9-418e-af19-bc1e50230072" />

### Apps
<img width="1075" height="745" alt="Apps" src="https://github.com/user-attachments/assets/9d83194e-1dd1-46e7-b8ed-f5e85ed9d9d1" />

## Features

- **Foreground-only tracking.** Background time is never counted. If you switched away, the clock stops.
- **Idle detection.** Configurable idle threshold (default 5 minutes) pauses tracking when you step away.
- **Dashboard.** Live view of what you are currently using, today's total, this week's total, and your top apps.
- **Calendar view.** Browse usage by day to spot patterns over time.
- **Per-app detail.** Open any app to see its full session history and totals.
- **Rewards system.** An always-on progression layer that works out of the box — no setup. Daily goals reward your total tracked time and app launches with XP, levels, credits, and crafting resources. Rewards are applied automatically (no manual claiming). Can be disabled entirely.
- **Neon Village mini-game.** Spend the resources you earn to build and upgrade a village. Buildings have real effects: the **workshop** boosts XP gains, **storage** raises your resource cap, **houses** add villagers who generate resources every day, and the **tavern** boosts streak rewards. It forms a satisfying loop: use your apps → earn resources → build → earn faster.
- **Streak tracking.** Keeps a daily streak for favorite apps (30+ minutes of focused use) and pays out one-time bonus rewards at 3, 7, 14, and 30 days.
- **Theme presets.** Several accent color options. Changes apply on next launch.
- **System tray and autostart.** Minimize to tray and optionally launch at login via the Windows registry.
- **Data export.** Export your history to CSV or JSON. Backup and restore the SQLite database directly.
- **In-app updates.** Ships with a default GitHub releases feed, so update checks work out of the box — check manually or automatically on startup.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer (for running from source)

## Installation

Download the latest release from the [Releases](../../releases) page.

**Standard installer (recommended)**

1. Download `AppTrackr_Setup.exe`.
2. Run the installer and follow the prompts.
3. Launch AppTrackr from the Start Menu or desktop shortcut.

**Portable build**

1. Download `AppTrackr_Portable.zip`.
2. Extract it anywhere.
3. Run `AppTrackr.exe`.

## Developer Setup

Clone the repo and install in editable mode with dev dependencies:

```bash
pip install -e ".[dev]"
```

Run the app:

```bash
python -m apptrackr
```

### Running the tests

The core logic (analytics queries, rollups, rewards, the village economy, data
export, and the updater) is covered by a platform-independent pytest suite that
runs on Windows, macOS, and Linux — no GUI or Win32 dependencies required:

```bash
pip install pytest psutil
python -m pytest
```

CI runs this suite on every push (`.github/workflows/tests.yml`) across Python
3.10–3.12.

### Custom data location

By default the SQLite database lives in `%APPDATA%\AppTrackr`. Set the
`APPTRACKR_DATA_DIR` environment variable to relocate it — handy for portable
installs, separate profiles, or throwaway test runs.

## Building from Source

**PyInstaller bundle**

```bash
pyinstaller packaging/apptrackr.spec
```

**Inno Setup installer**

1. Open `packaging/installer.iss` in Inno Setup.
2. Compile the script.
3. The installer is written to `packaging/Output/AppTrackr_Setup.exe`.

## Release Automation

The workflow at `.github/workflows/release-windows.yml` handles the full build and publish pipeline. Push a version tag to trigger it:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow builds the PyInstaller bundle, zips it as a portable archive, compiles the Inno Setup installer, and uploads both to the GitHub release.

## Updates

Go to **Settings > Updates**, paste in the releases API URL, and click **Check for Updates**. Enable the startup check if you want it to run automatically.

For this repo, the URL is:

```
https://api.github.com/repos/H4ch1Net/AppTrackr/releases/latest
```

If AppTrackr finds a newer version it will offer to download and launch the installer for you.

## Privacy

Window titles are off by default. If you enable title tracking in Settings, titles are hashed (SHA-256, truncated) before storage so the raw text is never saved. Mouse click counts are optional and stored as counts only, with no position or content data.

## License

[MIT](LICENSE)
