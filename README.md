# SecuritySpy Image Downloader (Indigo Plugin)

An [Indigo](https://www.indigodomo.com/) plugin that downloads still images from [SecuritySpy](https://www.bensoftware.com/securityspy/) cameras (or any URL) so your automations can use them — most commonly to attach camera snapshots to notifications (e.g. Pushover) when a trigger fires.

## Features

- **Single image download** from a SecuritySpy camera or any custom URL (with optional basic/digest authentication)
- **Multi-camera stitching** — combine up to 10 cameras into one image, arranged as a vertical stack, a horizontal row, or a 2-column grid
- **Animated GIFs** — capture 2–10 seconds of frames from a camera and save them as an animated GIF
- **Resizing** — bound images to a maximum width; for SecuritySpy cameras the resize happens on the SecuritySpy server itself (faster, less bandwidth), for custom URLs it happens locally
- **Automatic camera discovery** from both major SecuritySpy Indigo plugins, with a manual camera-number fallback

## Requirements

- Indigo 2023.2 or later
- A SecuritySpy server with its web server enabled (only needed for SecuritySpy sources — custom-URL downloads work without any SecuritySpy configuration)
- Python dependencies (`requests`, `Pillow`) are **installed automatically by Indigo** from the plugin's bundled requirements when the plugin first starts — no manual pip step

## Installation

1. Download the latest release and double-click the `.indigoPlugin` bundle; Indigo installs and enables it.
2. Open the plugin's config dialog (Plugins → Image Downloader and SecuritySpy Helper → Configure...).

## Plugin Configuration

| Setting | Notes |
| --- | --- |
| SecuritySpy IP / Port | The SecuritySpy web server address (default port 8000, or as configured in SecuritySpy). Leave **both blank** if you only download from custom URLs. |
| Use SSL | Enable if SecuritySpy's web server uses HTTPS. |
| Verify SSL certificates | Off by default — self-signed certificates are typical for SecuritySpy. Enable only with a trusted certificate. Also applies to custom-URL downloads. |
| Login / Password | SecuritySpy web server credentials, if required. |
| Debug | Verbose logging; takes effect immediately, including at plugin startup. |

## Camera Discovery

Camera dropdowns are populated automatically from either (or both) of:

- **Cynical SecuritySpy** (`org.cynic.indigo.securityspy`)
- **SecuritySpy / Spy Connect by FlyingDiver** (`com.flyingdiver.indigoplugin.securityspy`)

If neither plugin is installed, the dropdown falls back to manual camera numbers (0–15). Find a camera's number in the SecuritySpy web interface — it's the `cameraNum` value in the URL when viewing that camera.

## Actions

### Download URL/SecuritySpy Image

Downloads a single image to a file.

- **Source**: a SecuritySpy camera, or a custom URL (supports `%%v:variableId%%` variable substitution and basic/digest auth)
- **Destination**: a full file path, entered directly or read from an Indigo variable
- **Max Width**: optional resize; SecuritySpy sources are resized by the server (aspect ratio preserved), custom URLs are resized locally
- **Animated GIF**: instead of a single image, capture frames (one every 2 seconds) for 2–10 seconds and save a `.gif` (the extension is corrected automatically); frames can optionally play in reverse
- **Hide from Indigo log**: suppress the success log line

The image file is guaranteed to exist on disk when the action completes, so a following action (e.g. a notification with attachment) can use it immediately.

### Download and Stitch Multiple SecuritySpy Images

Downloads 2–10 SecuritySpy camera images and combines them into a single file.

- **Layout**: vertical stack (default), horizontal row, or 2-column grid — cameras are placed in selection order
- **Max Width**: applied per camera image (server-side), keeping mixed-resolution cameras consistent
- Cameras that fail to download are skipped with a warning; the stitch proceeds with the rest

## Example: camera snapshot in a Pushover notification

1. Create an Indigo variable per camera holding a snapshot path, e.g. `front_door_snapshot` = `/Users/you/Documents/CameraImages/front_door.jpg`
2. Create a "Download URL/SecuritySpy Image" action for the camera, using the variable (`%%v:VARIABLEID%%` or the variable picker) as the destination
3. Create your Pushover (or similar) notification action with the same path as the attachment
4. Tie them together in a trigger: *motion detected while away → download snapshot → send notification*

## Troubleshooting

- Enable **Debug** in the plugin config for verbose logging.
- The plugin's own log lives at `/Library/Application Support/Perceptive Automation/Indigo <version>/Logs/com.vtmikel.securityspyimage/plugin.log`.
- A "SecuritySpy connection not configured" error means a SecuritySpy-camera action ran without the IP/port set — custom-URL actions never need that.
- If a stitch produces fewer cameras than expected, check the log for per-camera "Skipping camera" warnings.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest      # 130+ tests, no network required
black .               # formatting
```

Bug reports and PRs: https://github.com/mlamoure/indigo-securityspy-image-downloader
