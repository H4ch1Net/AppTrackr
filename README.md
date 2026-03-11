# AppTrackr

Desktop app usage time tracker with neon UI and gamification.

## Features
- Foreground window time tracking (Steam playtime style, for any app)
- Daily/weekly analytics, calendar heatmap
- Rewards & Neon Village mini-game
- System tray integration, autostart
- Sleek neon-themed UI (PySide6)

## Quick Start

```bash
pip install -e ".[dev]"
python -m apptrackr
```

## Install For Users

### Option A (Recommended): One-Click Installer

1. Go to the latest GitHub release under the `H4ch1Net` account.
2. Download `AppTrackr_Setup.exe`.
3. Run it and click through the installer.
4. Launch `AppTrackr` from Start Menu or desktop shortcut.

This is the easiest and most normal Windows install flow.

### Option B (No Install): Portable Build

1. Download `AppTrackr_Portable.zip` from the same release page.
2. Extract the zip anywhere (for example `C:\Apps\AppTrackr`).
3. Run `AppTrackr.exe` from the extracted folder.

This is optional for users who do not want a normal installed app.

## Launching

- Installed build: Start Menu -> `AppTrackr`
- Developer run: `python -m apptrackr`

## Updating

- Manual update: run the latest `AppTrackr_Setup.exe` over the current installation.
- In-app update checks:
	- Go to `Settings -> Updates`
	- Set `Update feed URL` to your latest-release API endpoint
	- Click `Check for Updates`
	- Enable `Automatically check for updates on startup`

Example feed URL (replace repo name as needed):

`https://api.github.com/repos/H4ch1Net/<repo>/releases/latest`

## Publish Releases (Maintainer)

The repo includes a GitHub Actions workflow at `.github/workflows/release-windows.yml`.

- It builds both:
	- `AppTrackr_Setup.exe` (normal installer)
	- `AppTrackr_Portable.zip` (portable/no-install)
- It uploads both files to the GitHub Release.

Trigger it by pushing a version tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Packaging

```bash
pyinstaller packaging/apptrackr.spec
```

Then open `packaging/installer.iss` with Inno Setup and build `AppTrackr_Setup.exe`.
