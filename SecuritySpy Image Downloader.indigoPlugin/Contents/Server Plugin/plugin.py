import datetime
import os
import shutil
import time

import requests
from PIL import Image
from requests.auth import HTTPDigestAuth, HTTPBasicAuth

try:
    import indigo
except ImportError:
    pass

DEFAULT_UPDATE_FREQUENCY = 24  # frequency (hours) between update checks
REQUEST_TIMEOUT = 30


class Plugin(indigo.PluginBase):
    """
    Indigo plugin for downloading images from SecuritySpy (or other sources),
    stitching them together, generating GIFs, etc.
    """

    def __init__(
        self,
        plugin_id: str,
        plugin_display_name: str,
        plugin_version: str,
        plugin_prefs: dict,
    ) -> None:
        """
        Initialize the Plugin with Indigo-specific parameters.
        """
        super(Plugin, self).__init__(
            plugin_id, plugin_display_name, plugin_version, plugin_prefs
        )

        self.security_spy_ip: str | None = plugin_prefs.get("ip", None)
        self.security_spy_port: str | None = plugin_prefs.get("port", None)
        self.security_spy_login: str | None = plugin_prefs.get("login", None)
        self.security_spy_pass: str | None = plugin_prefs.get("password", None)
        self.use_ssl: bool = plugin_prefs.get("ssl", False)
        self.security_spy_auth_type: str | None = (
            "basic" if self.security_spy_login else None
        )

        # Track version and updates
        self.last_update_check: datetime.datetime | None = None
        self.plugin_version: str = plugin_version

        # Construct the SecuritySpy URL
        self.update_url()

        # Log initialization
        self.debug_log("Plugin initialized.")

    def debug_log(self, message: str) -> None:
        """
        Log a debug message if debugging is enabled.
        """
        if self.debug:
            self.logger.debug(message)

    def update_url(self) -> None:
        """
        Construct the base SecuritySpy URL from the plugin preferences.
        """
        self.configured: bool = (
            self.security_spy_ip is not None and self.security_spy_port is not None
        )
        if self.use_ssl:
            self.security_spy_url = (
                f"https://{self.security_spy_ip}:{self.security_spy_port}"
            )
        else:
            self.security_spy_url = (
                f"http://{self.security_spy_ip}:{self.security_spy_port}"
            )

    def startup(self) -> None:
        """
        Perform any required logic at plugin startup.
        """
        self.debug_log("Plugin startup called")

    def closedPrefsConfigUi(self, valuesDict: dict, userCancelled: bool) -> None:
        """
        Handle actions after plugin preferences dialog is closed.
        Preserve method name as requested.
        """
        if not userCancelled:
            self.debug = valuesDict["debug"]
            self.security_spy_ip = valuesDict["ip"]
            self.security_spy_port = valuesDict["port"]
            self.security_spy_login = valuesDict["login"]
            self.security_spy_pass = valuesDict["password"]
            self.use_ssl = valuesDict["ssl"]

            self.security_spy_auth_type = None
            if len(self.security_spy_login) > 0:
                self.security_spy_auth_type = "basic"

            # Re-build the SecuritySpy URL with any updated prefs
            self.update_url()

    def shutdown(self) -> None:
        """
        Handle any required shutdown actions for the plugin.
        """
        self.debug_log("Plugin shutdown called")

    def prepare_text_value(self, input_string: str | None) -> bytes | None:
        """
        Trim and substitute Indigo variables, then UTF-8 encode the string.
        Returns the encoded bytes, or None if input_string is None.
        """
        if input_string is None:
            return None

        cleaned_string = input_string.strip()
        cleaned_string = self.substitute(cleaned_string)
        return cleaned_string.encode("utf-8")

    def get_image(
        self,
        url: str,
        save: str,
        auth_type: str | None = None,
        login: str | None = None,
        password: str | None = None,
    ) -> bool:
        """
        Download an image from a URL and save it locally.
        Supports optional basic/digest authentication.
        Returns True on success, False on failure.
        """
        # Ensure the destination path is a string (decode if needed)
        try:
            save = save.decode("utf-8")
        except (UnicodeDecodeError, AttributeError):
            pass

        # Log if desired or if debug is on
        self.logger.info(f"fetched image from {url} and saving it to: '{save}'")
        self.logger.debug(f"fetched image URL: {url}")

        # Determine the proper auth handler
        if auth_type is None:
            auth = None
        elif auth_type == "basic":
            auth = HTTPBasicAuth(login, password)
        elif auth_type == "digest":
            auth = HTTPDigestAuth(login, password)
        else:
            self.logger.error("Unsupported auth type.")
            return False

        try:
            response = requests.get(
                url,
                stream=True,
                timeout=100,
                verify=False,
                auth=auth,
            )
            # Raise an HTTPError if one occurred
            response.raise_for_status()

            with open(save, "wb") as f:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, f)

            response.close()
            return True

        except requests.exceptions.HTTPError as e:
            self.logger.error(f"error fetching image. HTTP error: {e}")
        except requests.exceptions.Timeout:
            self.logger.error("the request timed out.")
        except Exception as e:
            self.logger.error(f"error fetching image. error: {e}")

        # If we reach here, it failed.
        return False

    def stitch_images(self, images: list[Image.Image]) -> Image.Image:
        """
        Combine multiple PIL Image objects vertically into a single image.
        Returns the resulting stitched image.
        """
        result_height: int = 0
        result_width: int = 0

        # Determine final width and height
        for image in images:
            width, height = image.size
            result_height += height
            if width > result_width:
                result_width = width

        # Create a new image canvas
        result = Image.new("RGB", (result_width, result_height))
        cur_height: int = 0

        # Paste each image in vertically
        for image in images:
            width, height = image.size
            result.paste(im=image, box=(0, cur_height))
            cur_height += height

        return result

    def stitch_image_action(
        self, plugin_action: indigo.PluginAction, dev: indigo.Device
    ) -> bool:
        """
        Download multiple camera images, stitch them vertically, and save the result.
        Returns True if successful, False otherwise.
        """
        if not self.configured:
            return False

        start_time = time.time()

        # Get the destination file path
        destination_file = None
        use_variable = plugin_action.props.get("useVariable", False)
        try:
            if use_variable:
                destination_file = indigo.variables[
                    int(plugin_action.props["destinationVariable"])
                ].value
            else:
                destination_file = self.prepare_text_value(
                    plugin_action.props["destination"]
                )
        except Exception:
            destination_file = self.prepare_text_value(
                plugin_action.props["destination"]
            )

        if isinstance(destination_file, bytes):
            destination_file = destination_file.decode("utf-8")
        if not destination_file:
            self.logger.error("Destination file path not provided.")
            return False

        # Check that the directory exists
        dest_dir = os.path.dirname(destination_file)
        if not os.path.exists(dest_dir):
            self.debug_log(f"Path does not exist: {dest_dir}")
            return False

        # Prepare list of images to be stitched
        temp_directory = dest_dir
        images = []

        # Iterate through up to 10 cameras
        for i in range(1, 11):
            cam_key = f"cam{i}"
            cam_prop = plugin_action.props.get(cam_key, "")
            if cam_prop in ("-1", ""):
                self.debug_log("skipping camera")
                continue

            camera_dev_id = None
            camera_name = ""
            # Locate the camera device
            for camera in indigo.devices.iter(
                filter="org.cynic.indigo.securityspy.camera"
            ):
                if camera.enabled:
                    camera_num = camera.address[
                        camera.address.find("(") + 1 : camera.address.find(")")
                    ]
                    if camera_num == cam_prop:
                        camera_dev_id = camera.id
                        camera_name = camera.name
                        break

            # Build the URL for this camera
            image_url = f"{self.security_spy_url}/++image?cameraNum={cam_prop}"
            image_file = os.path.join(temp_directory, f"temp{i}.jpg")

            # Fetch each camera image
            success = self.get_image(
                url=image_url,
                save=image_file,
                auth_type=self.security_spy_auth_type,
                login=self.security_spy_login,
                password=self.security_spy_pass,
            )
            if not success:
                self.debug_log(
                    f"error obtaining image for camera '{camera_name}', skipping"
                )
                continue

            # Optionally resize
            try:
                with Image.open(image_file) as img:
                    if "imageSize" in plugin_action.props:
                        try:
                            max_width = int(plugin_action.props["imageSize"])
                            if max_width > 0:
                                indigo.server.log(
                                    f"resized '{camera_name}' camera image to max width of {max_width}px"
                                )
                                img.thumbnail((max_width, 100000))
                        except ValueError:
                            pass

                    # Add the final copy of the image to the list
                    images.append(img.copy())
            except Exception as e:
                self.debug_log(
                    f"error opening or resizing image for camera '{camera_name}': {e}"
                )
                continue

        # If no images were retrieved, log an error and return False
        if not images:
            self.logger.error("No images to stitch.")
            return False

        # Stitch all retrieved images
        stitched_image = self.stitch_images(images)
        stitched_image.save(destination_file)

        # Log results
        total_time = round(time.time() - start_time, 2)
        file_size_kb = os.path.getsize(destination_file) >> 10
        file_size_str = f"{file_size_kb} KB"
        indigo.server.log(
            f"stitched {len(images)} camera images and saved to: {destination_file} "
            f"({file_size_str}).  Total time: {total_time} seconds."
        )

        # Clean up temporary files
        for i in range(1, 11):
            temp_path = os.path.join(temp_directory, f"temp{i}.jpg")
            try:
                os.remove(temp_path)
                self.debug_log(f"deleting file {temp_path}")
            except Exception:
                pass

        return True

    def camera_list_generator(
        self,
        filter: str = "",
        valuesDict: dict | None = None,
        typeId: str = "",
        targetId: int = 0,
    ) -> list[tuple[str, str]]:
        """
        Generate a list of cameras for UI selection.
        Returns a list of (camera_number, camera_name) tuples.
        """
        filter_list_ui: list[tuple[str, str]] = []

        # Gather enabled SecuritySpy cameras
        for camera in indigo.devices.iter(filter="org.cynic.indigo.securityspy.camera"):
            if camera.enabled:
                camera_name = camera.name
                camera_num = camera.address[
                    camera.address.find("(") + 1 : camera.address.find(")")
                ]
                filter_list_ui.append((camera_num, camera_name))

        # If no cameras found, create placeholders for up to 16
        if not filter_list_ui:
            for i in range(16):
                filter_list_ui.append((str(i), f"Camera {i}"))

        # Always include the 'none' option
        filter_list_ui.append(("-1", "none"))

        return filter_list_ui

    def download_image_action(
        self, plugin_action: indigo.PluginAction, dev: indigo.Device
    ) -> bool:
        """
        Download a single image (or multiple frames for an animated GIF) from the configured source.
        Returns True on success, False otherwise.
        """
        if not self.configured:
            return False

        start_time: float = time.time()
        hide_log: bool = plugin_action.props.get("hidelog", False)

        #
        # --- STEP 1: Determine destination file ---
        #
        try:
            if plugin_action.props["useVariable"]:
                destination_file = indigo.variables[
                    int(plugin_action.props["destinationVariable"])
                ].value
            else:
                destination_file = self.prepare_text_value(
                    plugin_action.props["destination"]
                )
        except Exception:
            destination_file = self.prepare_text_value(
                plugin_action.props["destination"]
            )

        if not destination_file:
            self.logger.error("Destination file path not provided.")
            return False

        # Check that the destination directory exists
        dest_dir = os.path.dirname(destination_file)
        if not os.path.exists(dest_dir):
            self.logger.error(f"path does not exist: {dest_dir}")
            return False

        #
        # --- STEP 2: Determine image source, camera info, and build URL ---
        #
        camera_dev_id = None
        camera_name = ""
        image_url = ""

        # If using SecuritySpy
        if plugin_action.props["type"] == "securityspy":
            # Try to find the desired camera
            for camera in indigo.devices.iter(
                filter="org.cynic.indigo.securityspy.camera"
            ):
                if camera.enabled:
                    camera_num = camera.address[
                        camera.address.find("(") + 1 : camera.address.find(")")
                    ]
                    if camera_num == plugin_action.props["cam1"]:
                        camera_dev_id = camera.id
                        camera_name = camera.name
                        break
            # Construct the SecuritySpy image URL
            image_url = f"{self.security_spy_url}/++image?cameraNum={plugin_action.props['cam1']}"
        else:
            # If not SecuritySpy, assume direct URL
            raw_url = plugin_action.props.get("url", "")
            processed_url = self.prepare_text_value(raw_url) or b""
            image_url = processed_url.decode("utf-8", errors="ignore")

        #
        # --- STEP 3: Determine requested image size for optional resizing ---
        #
        image_size: int = -1
        try:
            size_prop = plugin_action.props.get("imageSize", "")
            if size_prop and int(size_prop):
                image_size = int(size_prop)
        except ValueError:
            self.logger.error("error with the resize, must be an integer.")
            image_size = -1

        #
        # --- STEP 4: Determine authentication for get_image ---
        #
        get_image_auth = self.security_spy_auth_type
        get_image_login = self.security_spy_login
        get_image_password = self.security_spy_pass
        if plugin_action.props["type"] == "urlType":
            # Possibly override with other auth choices
            if plugin_action.props.get("useAuth") in (None, "none"):
                get_image_auth = None
            else:
                get_image_auth = plugin_action.props["useAuth"]
                get_image_login = plugin_action.props.get("login", None)
                get_image_password = plugin_action.props.get("password", None)

        #
        # --- Helper function for resizing ---
        #
        def resize_image_if_needed(
            img_path: str, final_path: str, max_width: int
        ) -> None:
            """
            Resize the image at img_path if max_width > 0, then save to final_path.
            """
            with Image.open(img_path) as img:
                if max_width > 0:
                    img.thumbnail((max_width, 100000))
                img.save(final_path)

        #
        # --- STEP 5: Single image download or animated GIF creation ---
        #
        if not plugin_action.props.get("gif"):
            #
            # Single image logic
            #
            temp_directory = os.path.dirname(destination_file)
            # Save directly if no resizing is needed, else save to temp first
            if image_size > 0:
                temp_path = os.path.join(temp_directory, "temp_forResize.jpg")
            else:
                temp_path = destination_file

            try:
                self.get_image(
                    url=image_url,
                    save=temp_path,
                    auth_type=get_image_auth,
                    login=get_image_login,
                    password=get_image_password,
                )
            except Exception:
                self.logger.info(
                    "error fetching the image, not proceeding with resizing"
                )
                return False

            # If resizing was requested, handle it now
            if image_size > 0 and os.path.exists(temp_path):
                resize_image_if_needed(temp_path, destination_file, image_size)
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

            # Log success if logs are not hidden
            if not hide_log:
                source_str = f"'{camera_name}'" if camera_name else f"'{image_url}'"
                self.logger.info(
                    f"fetched image from {source_str}, resized, and saved it to: {destination_file}"
                )
        else:
            #
            # Animated GIF logic
            #
            quality: int = 60
            # Ensure file is a string and has .gif extension
            if isinstance(destination_file, bytes):
                destination_file = destination_file.decode("utf-8")
            if not destination_file.lower().endswith(".gif"):
                base_path, _ = os.path.splitext(destination_file)
                destination_file = base_path + ".gif"

            temp_directory = os.path.dirname(destination_file)
            filenames: list[str] = []
            i: int = 0

            # Determine how long total to capture GIF frames
            try:
                total_gif_time = int(plugin_action.props.get("gifTime", 4))
            except ValueError:
                total_gif_time = 4

            # Capture frames every 2 seconds
            while i * 2.0 <= total_gif_time:
                if i != 0:
                    # Wait until we reach the next 2-second interval
                    elapsed = round(time.time() - start_time, 2)
                    sleep_time = (2 * i) - elapsed
                    self.debug_log(f"elapsed={elapsed}s, next frame in {sleep_time}s")
                    time.sleep(max(0, sleep_time))

                temp_filename = os.path.join(temp_directory, f"temp_forGif{i}.jpg")
                self.get_image(
                    url=image_url,
                    save=temp_filename,
                    auth_type=get_image_auth,
                    login=get_image_login,
                    password=get_image_password,
                )

                # Resize if needed
                if image_size > 0 and os.path.exists(temp_filename):
                    resize_image_if_needed(temp_filename, temp_filename, image_size)

                filenames.append(temp_filename)
                i += 1

            # Read frames from disk, then remove the temp files
            frames: list[Image.Image] = []
            for f_name in filenames:
                try:
                    with Image.open(f_name) as frame_img:
                        frames.append(frame_img.copy())
                except Exception:
                    pass
                try:
                    os.remove(f_name)
                except Exception:
                    pass

            if not frames:
                self.logger.error("No frames captured; cannot create GIF.")
                return False

            if plugin_action.props.get("reverseFrames", False):
                frames.reverse()
            # Save frames as an animated GIF
            frames[0].save(
                destination_file,
                save_all=True,
                append_images=frames[1:],
                duration=300,
                loop=0,
                quality=quality,
            )

            # Log final details
            file_size_kb = os.path.getsize(destination_file) >> 10
            file_size_str = f"{file_size_kb} KB"
            elapsed = round(time.time() - start_time, 2)
            if not hide_log:
                source_str = f"'{camera_name}'" if camera_name else f"'{image_url}'"
                self.logger.info(
                    f"fetched images from {source_str}, created an animated gif "
                    f"({total_gif_time}s, {i} frames), saved to: {destination_file} "
                    f"({file_size_str}).  Total time: {elapsed}s."
                )

        return True
