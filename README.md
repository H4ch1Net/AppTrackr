# AppTrackr

Track where your time actually goes on Windows, one focused window at a time.

AppTrackr is a Windows-first desktop application for foreground app usage tracking, analytics, update delivery, and an optional gamified rewards loop.

## ✨ Highlights

- Accurate foreground-only tracking (no inflated background time)
- Clean daily and weekly usage analytics
- Calendar-style activity view
- Optional rewards and mini-game systems
- Tray support, autostart, and in-app update checks
- Neon UI with theme presets

## Core Features

- 🕒 **Foreground Tracking**: Time is counted only while an app is focused.
- 📊 **Analytics**: View top apps, rollups, and trends.
- 📅 **Calendar View**: Scan your usage patterns by day.
- 🎮 **Rewards (Optional)**: Enable or disable per-app reward progression.
- 🔄 **Updates**: Manual and automatic release checks from GitHub.
- 🎨 **Themes**: Switch accent color presets from Settings.

## 🖼️ Screenshots

Replace these placeholders with your real screenshots.

## Dashboard
<img width="1073" height="737" alt="{431FD81B-B68E-4BCB-96A6-52BDF4A4AC81}" src="https://github.com/user-attachments/assets/9321c718-12b5-4900-bf14-4b7efd1281f4" />



## Calendar
<img width="1078" height="744" alt="{1FCC47E2-6700-4421-8C2A-F0F119DAADD3}" src="https://github.com/user-attachments/assets/0051ab63-14c9-418e-af19-bc1e50230072" />



## Apps
<img width="1075" height="745" alt="{4CC7C304-8189-4984-9CAA-E07EFE9FE8F8}" src="https://github.com/user-attachments/assets/9d83194e-1dd1-46e7-b8ed-f5e85ed9d9d1" />

## Requirements

- Windows 10/11
- Python 3.10+

## Developer Setup

Clone the repository and install dependencies:

```bash
pip install -e ".[dev]"
```

Run the app in development mode:

```bash
python -m apptrackr
```

## 📦 Release Artifacts

Each release publishes two user install options:

- `AppTrackr_Setup.exe` for a standard Windows installation
- `AppTrackr_Portable.zip` for no-install portable usage

## End-User Installation

Two distribution options are provided from Releases.

### Recommended: Standard Installer

1. Download `AppTrackr_Setup.exe`.
2. Run the installer.
3. Launch AppTrackr from Start Menu or desktop shortcut.

### Optional: Portable Build

1. Download `AppTrackr_Portable.zip`.
2. Extract it to any folder.
3. Run `AppTrackr.exe` directly.

## Updates

AppTrackr supports manual and automatic update checks.

In `Settings -> Updates`:

1. Set `Update feed URL` to the repository releases API endpoint.
2. Click `Check for Updates` for on-demand checks.
3. Enable `Automatically check for updates on startup` if desired.

For this repo, use:

`https://api.github.com/repos/H4ch1Net/AppTrackr/releases/latest`

Generic format (for forks/custom repos):

`https://api.github.com/repos/<owner>/<repo>/releases/latest`

## Packaging (Windows)

Build the app bundle with PyInstaller:

```bash
pyinstaller packaging/apptrackr.spec
```

Build the installer with Inno Setup:

1. Open `packaging/installer.iss`.
2. Compile the script.
3. Output: `AppTrackr_Setup.exe`.

## Release Automation

The workflow at `.github/workflows/release-windows.yml` builds and publishes:

- `AppTrackr_Setup.exe`
- `AppTrackr_Portable.zip`

Trigger a release by pushing a version tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```
