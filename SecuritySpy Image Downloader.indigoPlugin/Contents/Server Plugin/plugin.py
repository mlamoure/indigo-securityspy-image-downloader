"""Indigo plugin adapter for the SecuritySpy Image Downloader.

Thin layer over the Indigo-free `securityspy_image` package: this module
handles Indigo lifecycle, preferences, and action callbacks; downloading and
image processing live in the package.
"""

import logging
import os
import socket
import time
from typing import List, Optional, Tuple

import indigo

from securityspy_image import cameras, http_client, image_ops
from securityspy_image.exceptions import DestinationError, SecuritySpyImageError

GIF_FRAME_INTERVAL = 2.0  # seconds between GIF frame captures
DEFAULT_GIF_SECONDS = 4
MAX_CAMERAS = 10  # maximum cameras supported for stitching
PREFS_CONNECT_TIMEOUT = 3  # seconds for the validate-prefs connectivity probe


def _remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


class Plugin(indigo.PluginBase):
    """Downloads images from SecuritySpy (or arbitrary URLs), stitches
    multi-camera snapshots, and assembles animated GIFs."""

    def __init__(
        self,
        plugin_id: str,
        plugin_display_name: str,
        plugin_version: str,
        plugin_prefs: dict,
    ) -> None:
        super().__init__(plugin_id, plugin_display_name, plugin_version, plugin_prefs)
        self.plugin_file_handler.setLevel(logging.DEBUG)
        self._apply_prefs(plugin_prefs)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self) -> None:
        self.logger.debug("Plugin startup called")

    def shutdown(self) -> None:
        self.logger.debug("Plugin shutdown called")

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def _apply_prefs(self, prefs) -> None:
        """Load connection settings and log level from `prefs` (plugin_prefs
        at startup, the dialog values dict after a config save)."""
        self.debug: bool = bool(prefs.get("debug", False))
        self.indigo_log_handler.setLevel(logging.DEBUG if self.debug else logging.INFO)

        self.security_spy_ip: str = prefs.get("ip") or ""
        self.security_spy_port: str = prefs.get("port") or ""
        self.security_spy_login: str = prefs.get("login") or ""
        self.security_spy_pass: str = prefs.get("password") or ""
        self.use_ssl: bool = bool(prefs.get("ssl", False))
        self.verify_ssl: bool = bool(prefs.get("verify_ssl", False))

        # SecuritySpy uses basic auth when credentials are configured
        self.security_spy_auth_type: Optional[str] = (
            "basic" if self.security_spy_login.strip() else None
        )

        self._update_connection_url()

    def _update_connection_url(self) -> None:
        """Build the SecuritySpy base URL; sets self.configured."""
        self.configured: bool = bool(
            self.security_spy_ip.strip() and self.security_spy_port.strip()
        )
        if not self.configured:
            self.security_spy_url: str = ""
            return

        protocol = "https" if self.use_ssl else "http"
        self.security_spy_url = (
            f"{protocol}://{self.security_spy_ip}:{self.security_spy_port}"
        )
        self.logger.debug(f"SecuritySpy URL configured: {self.security_spy_url}")

    def validatePrefsConfigUi(self, values_dict):
        """Validate connection settings. A failed connectivity probe only
        warns — the server may simply be offline while configuring.

        Both fields empty is valid: the plugin stays unconfigured for
        SecuritySpy but custom-URL downloads still work.
        """
        errors = indigo.Dict()

        ip = (values_dict.get("ip") or "").strip()
        port = (values_dict.get("port") or "").strip()
        if not ip and not port:
            return (True, values_dict)

        if not ip:
            errors["ip"] = (
                "SecuritySpy IP or hostname is required "
                "(or clear both fields if you only use custom URLs)"
            )
        try:
            if not 1 <= int(port) <= 65535:
                raise ValueError
        except ValueError:
            errors["port"] = "Port must be an integer between 1 and 65535"

        if len(errors):
            return (False, values_dict, errors)

        try:
            socket.create_connection(
                (ip, int(port)), timeout=PREFS_CONNECT_TIMEOUT
            ).close()
        except OSError as exc:
            self.logger.warning(
                f"Could not reach SecuritySpy at {ip}:{port} ({exc}); saving settings anyway"
            )
        return (True, values_dict)

    def closedPrefsConfigUi(self, values_dict, user_cancelled: bool) -> None:
        if user_cancelled:
            return
        self._apply_prefs(values_dict)
        self.logger.debug(
            f"Configuration updated - SecuritySpy configured: {self.configured}"
        )

    # ------------------------------------------------------------------
    # Action helpers
    # ------------------------------------------------------------------

    def prepare_text_value(self, input_string: Optional[str]) -> Optional[str]:
        """Strip and run Indigo variable substitution (%%v:123%%) on a value."""
        if input_string is None:
            return None
        return self.substitute(input_string.strip())

    def _get_destination_path(self, plugin_action: indigo.PluginAction) -> str:
        """Resolve the destination file path from the action's props.

        Raises DestinationError if no path is configured or its directory
        does not exist.
        """
        destination_file: Optional[str] = None
        if plugin_action.props.get("useVariable", False):
            try:
                var_id = int(plugin_action.props["destinationVariable"])
                destination_file = indigo.variables[var_id].value
            except (KeyError, ValueError) as exc:
                self.logger.debug(
                    f"Destination variable lookup failed ({exc}); falling back to direct path"
                )
        if not destination_file:
            destination_file = self.prepare_text_value(
                plugin_action.props.get("destination", "")
            )

        if not destination_file:
            raise DestinationError("Destination file path not provided")

        dest_dir = os.path.dirname(destination_file)
        if not os.path.isdir(dest_dir):
            raise DestinationError(f"Destination directory does not exist: {dest_dir}")
        return destination_file

    def _get_image_size(self, plugin_action: indigo.PluginAction) -> int:
        """Return the max image width in pixels, or -1 when no resize requested."""
        size_prop = (plugin_action.props.get("imageSize") or "").strip()
        if not size_prop:
            return -1
        try:
            return int(size_prop)
        except ValueError:
            self.logger.error("Image size must be an integer, ignoring resize option")
            return -1

    def _get_auth_config(
        self, plugin_action: indigo.PluginAction
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (auth_type, login, password) for the action's source."""
        if plugin_action.props.get("type") == "urlType":
            use_auth = plugin_action.props.get("useAuth")
            if use_auth in (None, "none"):
                return None, None, None
            return (
                use_auth,
                plugin_action.props.get("login"),
                plugin_action.props.get("password"),
            )
        return (
            self.security_spy_auth_type,
            self.security_spy_login,
            self.security_spy_pass,
        )

    def _build_image_url(
        self, plugin_action: indigo.PluginAction, image_size: int = -1
    ) -> Tuple[str, str, bool]:
        """Return (image_url, camera_name, server_resized).

        camera_name is empty for custom URLs. For SecuritySpy sources with a
        max width, the resize happens server-side via the ++image width
        parameter and server_resized is True (no local PIL pass needed).
        """
        if plugin_action.props.get("type") == "securityspy":
            camera_id = plugin_action.props.get("cam1", "0")
            _, camera_name = self._get_camera_info(camera_id)
            _, camera_num = cameras.split_camera_id(camera_id)
            return (
                http_client.build_securityspy_image_url(
                    self.security_spy_url, camera_num, width=image_size
                ),
                camera_name,
                image_size > 0,
            )
        url = self.prepare_text_value(plugin_action.props.get("url", "")) or ""
        return url, "", False

    def _download_to_file(
        self,
        url: str,
        save_path: str,
        auth_type: Optional[str],
        login: Optional[str],
        password: Optional[str],
    ) -> None:
        """Download one image to disk; raises DownloadError on failure."""
        self.logger.debug(
            f"Downloading image from {http_client.sanitize_url(url)} to: '{save_path}'"
        )
        auth = http_client.build_auth(auth_type, login, password)
        size = http_client.download_image(
            url, save_path, auth=auth, verify_ssl=self.verify_ssl
        )
        self.logger.debug(f"Downloaded image: {size} bytes")

    # ------------------------------------------------------------------
    # Camera discovery (requires indigo)
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_device_type(camera, plugin_config: dict) -> bool:
        device_type_filter = plugin_config.get("device_type_filter")
        if device_type_filter and hasattr(camera, "deviceTypeId"):
            return camera.deviceTypeId == device_type_filter
        return True

    def _discover_cameras(self) -> List[Tuple[str, str, str]]:
        """Return (camera_number, camera_name, plugin_type) for every enabled
        camera across all supported SecuritySpy plugins."""
        discovered: List[Tuple[str, str, str]] = []
        for plugin_key, plugin_config in cameras.SECURITYSPY_PLUGINS.items():
            found = 0
            try:
                for camera in indigo.devices.iter(filter=plugin_config["filter"]):
                    if not camera.enabled:
                        continue
                    if not self._matches_device_type(camera, plugin_config):
                        continue
                    camera_num = plugin_config["address_parser"](camera.address)
                    if camera_num:
                        discovered.append((camera_num, camera.name, plugin_key))
                        found += 1
            except Exception:
                self.logger.exception(
                    f"Error discovering cameras from {plugin_config['name']}"
                )
            self.logger.debug(f"Found {found} cameras from {plugin_config['name']}")
        return discovered

    def _get_camera_info(self, camera_id: str) -> Tuple[Optional[int], str]:
        """Find the Indigo device for a camera ID, as (device_id, name).

        IDs are "plugin_type:camera_num"; bare numbers are legacy configs
        that predate multi-plugin support and map to the Cynical plugin.
        """
        plugin_type, camera_num = cameras.split_camera_id(camera_id)
        if plugin_type is None:
            self.logger.debug(
                f"Converting legacy camera ID '{camera_id}' to cynical:{camera_id}"
            )
            plugin_type = "cynical"

        plugin_config = cameras.SECURITYSPY_PLUGINS.get(plugin_type)
        if plugin_config is None:
            return None, ""

        try:
            for camera in indigo.devices.iter(filter=plugin_config["filter"]):
                if not camera.enabled:
                    continue
                if not self._matches_device_type(camera, plugin_config):
                    continue
                if plugin_config["address_parser"](camera.address) == camera_num:
                    return camera.id, camera.name
        except Exception:
            self.logger.exception(
                f"Error searching for camera {camera_num} in {plugin_config['name']}"
            )
        return None, ""

    def camera_list_generator(
        self,
        filter: str = "",  # noqa: A002 — name fixed by the Indigo callback API
        valuesDict: Optional[dict] = None,
        typeId: str = "",
        targetId: int = 0,
    ) -> List[Tuple[str, str]]:
        """Populate camera selection menus in action config dialogs."""
        camera_options: List[Tuple[str, str]] = []

        for camera_num, camera_name, plugin_type in self._discover_cameras():
            plugin_name = cameras.SECURITYSPY_PLUGINS[plugin_type]["name"]
            camera_options.append(
                (f"{plugin_type}:{camera_num}", f"{camera_name} ({plugin_name})")
            )

        def sort_key(option: Tuple[str, str]) -> int:
            camera_id = option[0]
            _, camera_num = cameras.split_camera_id(camera_id)
            return int(camera_num) if camera_num.isdigit() else 999

        camera_options.sort(key=sort_key)

        # Fallback when no SecuritySpy plugins are installed
        if not camera_options:
            self.logger.debug(
                "No SecuritySpy cameras found from any supported plugin, "
                "using fallback camera list"
            )
            for i in range(16):
                camera_options.append((str(i), f"Camera {i} (Manual)"))

        # Always include 'none' for optional camera slots
        camera_options.append(("-1", "none"))
        return camera_options

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def download_image_action(
        self, plugin_action: indigo.PluginAction, dev: indigo.Device
    ) -> bool:
        """Download a single image, or capture frames into an animated GIF.

        Only SecuritySpy sources need the SecuritySpy connection configured;
        custom-URL downloads work without it.
        """
        if plugin_action.props.get("type") == "securityspy" and not self.configured:
            self.logger.error(
                "SecuritySpy connection not configured - set the IP and port "
                "in the plugin config to use SecuritySpy cameras"
            )
            return False

        start_time = time.time()
        hide_log = plugin_action.props.get("hidelog", False)

        try:
            destination_file = self._get_destination_path(plugin_action)
            image_size = self._get_image_size(plugin_action)
            image_url, camera_name, server_resized = self._build_image_url(
                plugin_action, image_size
            )
            if not image_url:
                self.logger.error("Unable to determine image URL")
                return False
            if server_resized:
                image_size = -1  # SecuritySpy scales via the width param
            auth_type, login, password = self._get_auth_config(plugin_action)

            if plugin_action.props.get("gif", False):
                return self._create_animated_gif(
                    plugin_action,
                    destination_file,
                    image_url,
                    camera_name,
                    auth_type,
                    login,
                    password,
                    image_size,
                    start_time,
                    hide_log,
                )
            return self._download_single_image(
                destination_file,
                image_url,
                camera_name,
                auth_type,
                login,
                password,
                image_size,
                hide_log,
            )
        except SecuritySpyImageError as exc:
            self.logger.error(str(exc))
            return False

    def stitch_image_action(
        self, plugin_action: indigo.PluginAction, dev: indigo.Device
    ) -> bool:
        """Download multiple camera images and stitch them into one file."""
        if not self.configured:
            self.logger.error(
                "SecuritySpy connection not configured - set the IP and port "
                "in the plugin config to use the stitch action"
            )
            return False

        start_time = time.time()
        try:
            destination_file = self._get_destination_path(plugin_action)
        except SecuritySpyImageError as exc:
            self.logger.error(str(exc))
            return False

        image_size = self._get_image_size(plugin_action)
        layout = plugin_action.props.get("layout", image_ops.LAYOUT_VERTICAL)
        if layout not in image_ops.VALID_LAYOUTS:
            self.logger.warning(f"Unknown stitch layout '{layout}', using vertical")
            layout = image_ops.LAYOUT_VERTICAL

        temp_directory = os.path.dirname(destination_file)
        images = []

        for i in range(1, MAX_CAMERAS + 1):
            cam_prop = plugin_action.props.get(f"cam{i}", "")
            if cam_prop in ("-1", ""):
                continue

            _, camera_name = self._get_camera_info(cam_prop)
            _, camera_num = cameras.split_camera_id(cam_prop)
            # SecuritySpy scales server-side via the width param, so the
            # frames arrive already bounded — no local PIL resize needed.
            image_url = http_client.build_securityspy_image_url(
                self.security_spy_url, camera_num, width=image_size
            )
            temp_file = http_client.create_temp_file(temp_directory, f"stitch{i}")
            try:
                self._download_to_file(
                    image_url,
                    temp_file,
                    self.security_spy_auth_type,
                    self.security_spy_login,
                    self.security_spy_pass,
                )
                images.append(image_ops.load_image(temp_file))
            except SecuritySpyImageError as exc:
                self.logger.warning(
                    f"Skipping camera '{camera_name or cam_prop}': {exc}"
                )
            finally:
                _remove_quietly(temp_file)

        if not images:
            self.logger.error("No images to stitch.")
            return False

        stitched_image = image_ops.stitch(images, layout=layout)
        try:
            stitched_image.save(destination_file)
        except OSError as exc:
            self.logger.error(
                f"Failed to save stitched image to '{destination_file}': {exc}"
            )
            return False

        total_time = round(time.time() - start_time, 2)
        file_size_kb = os.path.getsize(destination_file) >> 10
        self.logger.info(
            f"stitched {len(images)} camera images ({layout} layout) and saved to: "
            f"{destination_file} ({file_size_kb} KB).  Total time: {total_time} seconds."
        )
        return True

    def _download_single_image(
        self,
        destination_file: str,
        image_url: str,
        camera_name: str,
        auth_type: Optional[str],
        login: Optional[str],
        password: Optional[str],
        image_size: int,
        hide_log: bool,
    ) -> bool:
        """Download one image, optionally bounding it to `image_size` wide."""
        if image_size > 0:
            download_path = http_client.create_temp_file(
                os.path.dirname(destination_file), "resize"
            )
        else:
            download_path = destination_file

        try:
            self._download_to_file(image_url, download_path, auth_type, login, password)
            if image_size > 0:
                image_ops.resize_to_width(download_path, destination_file, image_size)
        finally:
            if download_path != destination_file:
                _remove_quietly(download_path)

        if not hide_log:
            source_desc = (
                f"'{camera_name}'"
                if camera_name
                else f"'{http_client.sanitize_url(image_url)}'"
            )
            self.logger.info(
                f"Downloaded image from {source_desc} and saved to: {destination_file}"
            )
        return True

    def _create_animated_gif(
        self,
        plugin_action: indigo.PluginAction,
        destination_file: str,
        image_url: str,
        camera_name: str,
        auth_type: Optional[str],
        login: Optional[str],
        password: Optional[str],
        image_size: int,
        start_time: float,
        hide_log: bool,
    ) -> bool:
        """Capture frames over time and assemble them into an animated GIF.

        Runs synchronously on the action thread by design: callers rely on
        the file existing when the action returns.
        """
        if not destination_file.lower().endswith(".gif"):
            destination_file = os.path.splitext(destination_file)[0] + ".gif"

        temp_directory = os.path.dirname(destination_file)
        try:
            total_gif_time = int(
                plugin_action.props.get("gifTime", DEFAULT_GIF_SECONDS)
            )
        except (TypeError, ValueError):
            total_gif_time = DEFAULT_GIF_SECONDS

        frames = []
        frame_index = 0
        while frame_index * GIF_FRAME_INTERVAL <= total_gif_time:
            if frame_index > 0:
                elapsed = time.time() - start_time
                sleep_time = (GIF_FRAME_INTERVAL * frame_index) - elapsed
                if sleep_time > 0:
                    self.logger.debug(f"Waiting {sleep_time:.1f}s for next frame")
                    time.sleep(sleep_time)

            frame_file = http_client.create_temp_file(
                temp_directory, f"gif-frame{frame_index}"
            )
            try:
                self._download_to_file(
                    image_url, frame_file, auth_type, login, password
                )
                frames.append(image_ops.load_image(frame_file, max_width=image_size))
            except SecuritySpyImageError as exc:
                self.logger.warning(f"Failed to capture frame {frame_index}: {exc}")
            finally:
                _remove_quietly(frame_file)
            frame_index += 1

        reverse = bool(plugin_action.props.get("reverseFrames", False))
        if reverse:
            self.logger.debug("Reversing frame order for animated GIF")
        try:
            image_ops.save_animated_gif(frames, destination_file, reverse=reverse)
        except SecuritySpyImageError as exc:
            self.logger.error(str(exc))
            return False

        if not hide_log:
            file_size_kb = os.path.getsize(destination_file) >> 10
            elapsed = time.time() - start_time
            source_desc = (
                f"'{camera_name}'"
                if camera_name
                else f"'{http_client.sanitize_url(image_url)}'"
            )
            self.logger.info(
                f"Created animated GIF from {source_desc} "
                f"({total_gif_time}s, {len(frames)} frames) saved to: {destination_file} "
                f"({file_size_kb} KB). Total time: {elapsed:.1f}s"
            )
        return True
