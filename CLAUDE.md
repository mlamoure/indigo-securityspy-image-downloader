# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Indigo home automation plugin that downloads images from SecuritySpy (or other URLs), with capabilities for:
- Single image downloads from SecuritySpy cameras or arbitrary URLs
- Multi-camera image stitching (vertical concatenation)
- Animated GIF creation from time-lapse captures
- Image resizing and authentication support

## Architecture

The plugin follows the family pattern used by the other vtmikel plugins
(Roomie Remote, Just Add Power, Auto Lights): a thin Indigo adapter over an
Indigo-free core package.

### Layout (under `SecuritySpy Image Downloader.indigoPlugin/Contents/Server Plugin/`)

- **plugin.py** — thin adapter: Indigo lifecycle, preferences (including
  `validatePrefsConfigUi`), action callbacks, camera discovery (anything that
  needs the `indigo` module). Catches the package's typed exceptions and logs
  them; actions return bool.
- **securityspy_image/** — core package; **never imports `indigo`**:
  - `exceptions.py` — `SecuritySpyImageError` base → `DownloadError`,
    `DestinationError`, `ImageProcessingError`.
  - `http_client.py` — image downloading (streaming, injectable `session=`
    for tests), auth handler construction (basic/digest), SecuritySpy URL
    building (including the server-side `width` resize param), URL credential
    sanitization for safe logging, unique temp-file creation
    (`tempfile.mkstemp`).
  - `image_ops.py` — pure-PIL stitching (`stitch(images, layout)` with
    vertical / horizontal / 2-column grid layouts), LANCZOS resizing,
    animated GIF assembly.
  - `cameras.py` — address parsers for both SecuritySpy backends and the
    `SECURITYSPY_PLUGINS` registry; `split_camera_id` handles legacy IDs.
- **Actions.xml** — two actions: `downloadImage`, `stitchImage`.
- **PluginConfig.xml** — SecuritySpy connection settings, SSL + SSL-verify
  toggles, debug logging toggle.

### Conventions

- Logging goes through `self.logger` (`logging.getLogger("Plugin")`); the
  `debug` pref sets the `indigo_log_handler` level in `_apply_prefs`, which
  runs at `__init__` AND on config save — never gate logging on a separate
  flag.
- Actions run synchronously on the action thread **by design**: callers rely
  on the image file existing when the action returns. Do not move downloads
  or GIF capture to a background queue.
- SSL verification is off by default (`verify_ssl` pref) because self-signed
  certs are the norm for SecuritySpy; `InsecureRequestWarning` is suppressed
  only when verification is disabled.
- Only SecuritySpy-camera sources require the SecuritySpy connection to be
  configured; custom-URL downloads must keep working with blank IP/port
  (`validatePrefsConfigUi` accepts both fields empty, rejects partial).
- Resizing for SecuritySpy sources happens **server-side** via the `++image`
  `width` query param (verified live 2026-07-24: width-only preserves aspect
  ratio, e.g. 3072x1728 → 640x360). Local PIL resizing is only for custom
  URLs. If an old SecuritySpy ignores `width`, the benign fallback is a
  full-size image.
- Never log raw URLs that may embed credentials — use
  `http_client.sanitize_url`.
- Formatter: **Black** (defaults). Run `black .` before committing.

## SecuritySpy Integration

The plugin supports multiple SecuritySpy plugin backends (registry in
`securityspy_image/cameras.py`):

1. **Cynical SecuritySpy** (`org.cynic.indigo.securityspy.camera`)
   - Address format: `"Camera Name (camera_number)"` → parsed by
     `parse_cynical_address` (whitespace/zero-padding stripped, must be
     numeric)
2. **FlyingDiver SecuritySpy / Spy Connect** (`com.flyingdiver.indigoplugin.securityspy`)
   - Address format: `"{server_id}:{camera_number}"` → parsed by
     `parse_flyingdiver_address`; only `spyCamera` device types are cameras
     (`spyServer` devices are filtered out)

Camera IDs in action props are `"plugin_type:camera_num"`; bare numbers are
legacy configs that map to the Cynical backend (`_get_camera_info`). Camera
numbers build SecuritySpy URLs like `/++image?cameraNum=X`.

## Development Commands

### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate.fish   # fish; use activate for bash
pip install -r requirements.txt
```

### Testing
```bash
python -m pytest
```

`tests/conftest.py` installs an `indigo` stub into `sys.modules` before any
plugin import (same approach as Auto Lights / Roomie Remote). HTTP never hits
the network — tests inject `FakeSession` (or monkeypatch
`http_client.download_image`); PIL runs for real against temp images.

### Formatting
```bash
black .
```

### Deployment
Use the canonical deploy script (never scp/rsync manually):
```bash
/home/mike/programming/mike-local-development-scripts/deploy_indigo_plugin_to_server.sh \
    "SecuritySpy Image Downloader.indigoPlugin" \
    /home/mike/programming/indigo-securityspy-image-downloader
```
Then restart the plugin (`com.vtmikel.securityspyimage`) and check its own log
at `.../Logs/com.vtmikel.securityspyimage/plugin.log`, not the global
`Events.txt`.

## Key Configuration

### Plugin Settings (PluginConfig.xml)
- SecuritySpy IP/port, SSL, and SSL-certificate-verification settings
- Authentication credentials (login/password)
- Debug logging toggle (takes effect immediately at startup)

### Action Configuration
Both actions support:
- Variable-based or direct path destination files
- Image resizing by maximum width (LANCZOS)
- The download action additionally supports GIF creation (2–10s, frames
  captured every 2s), frame reversal, and basic/digest auth for custom URLs
- `hidelog` suppresses the success log line

## File Structure Notes

- Requirements exist in two places with DIFFERENT contents by design:
  - the bundle copy (`.../Server Plugin/requirements.txt`) is **runtime-only**
    (`requests`, `pillow`) — Indigo 2023.2+ auto-pip-installs this file into
    `Contents/Packages` on every end-user machine, so dev tools must never
    appear there;
  - the repo-root copy adds the dev deps (`pytest`, `black`).
  Keep the runtime pins identical between the two.
- Versioning: `PluginVersion` in `Info.plist` is CalVer (`YYYY.N.0`); bump on
  behavior-changing PRs. `CFBundleVersion` stays `1.0.0` (family convention).
