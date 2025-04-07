import datetime
import os
import shutil
import time
from distutils.version import LooseVersion

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

        # Plugin preferences
        self.debug: bool = plugin_prefs.get("debug", False)
        self.securityspy_ip: str | None = plugin_prefs.get("ip", None)
        self.securityspy_port: str | None = plugin_prefs.get("port", None)
        self.securityspy_login: str | None = plugin_prefs.get("login", None)
        self.securityspy_pass: str | None = plugin_prefs.get("password", None)
        self.use_ssl: bool = plugin_prefs.get("ssl", False)
        self.ss_auth_type: str | None = "basic" if self.securityspy_login else None

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
            self.securityspy_ip is not None and self.securityspy_port is not None
        )
        if self.use_ssl:
            self.securityspy_url = (
                f"https://{self.securityspy_ip}:{self.securityspy_port}"
            )
        else:
            self.securityspy_url = (
                f"http://{self.securityspy_ip}:{self.securityspy_port}"
            )

    def startup(self) -> None:
        """
        Perform any required logic at plugin startup.
        """
        self.debug_log("Plugin startup called")
        self.check_for_new_version()

    def closedPrefsConfigUi(self, valuesDict: dict, userCancelled: bool) -> None:
        """
        Handle actions after plugin preferences dialog is closed.
        Preserve method name as requested.
        """
        if not userCancelled:
            self.debug = valuesDict["debug"]
            self.securityspy_ip = valuesDict["ip"]
            self.securityspy_port = valuesDict["port"]
            self.securityspy_login = valuesDict["login"]
            self.securityspy_pass = valuesDict["password"]
            self.use_ssl = valuesDict["ssl"]

            self.ss_auth_type = None
            if len(self.securityspy_login) > 0:
                self.ss_auth_type = "basic"

            # Re-build the SecuritySpy URL with any updated prefs
            self.update_url()

    def check_for_new_version(self) -> None:
        """
        Check the plugin store for a newer plugin version.
        """
        plugin_id: str = self.pluginId
        self.last_update_check = datetime.datetime.now()

        # URLs to check for updates
        current_version_url = (
            "https://api.indigodomo.com/api/v2/"
            f"pluginstore/plugin-version-info.json?pluginId={plugin_id}"
        )
        store_detail_url = "https://www.indigodomo.com/pluginstore/{}/"

        try:
            reply = requests.get(current_version_url, timeout=5)
            reply.raise_for_status()
            reply_dict = reply.json()
            plugin_dict = reply_dict["plugins"][0]
            latest_release = plugin_dict["latestRelease"]

            # Compare with current plugin version
            if isinstance(latest_release, dict) and LooseVersion(
                latest_release["number"]
            ) > LooseVersion(self.plugin_version):
                self.logger.info(
                    f"A new version of the plugin (v{latest_release['number']}) "
                    f"is available at: {store_detail_url.format(plugin_dict['id'])}"
                )
        except Exception as exc:
            self.logger.error(str(exc))

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

    def runConcurrentThread(self) -> None:
        """
        Run a background thread that performs periodic checks or tasks.
        Preserve method name as requested.
        """
        self.logger.debug("Starting concurrent thread")
        self.sleep(1)

        try:
            while True:
                # Sleep for the default update frequency (plus a small buffer)
                self.sleep(DEFAULT_UPDATE_FREQUENCY + 1)

                # Check if we've passed the threshold to check for a new version
                if self.last_update_check is not None and self.last_update_check < (
                    datetime.datetime.now()
                    - datetime.timedelta(hours=DEFAULT_UPDATE_FREQUENCY)
                ):
                    self.check_for_new_version()
        except self.StopThread:
            self.logger.debug("Received StopThread")

    def get_image(
        self,
        url: str,
        save: str,
        log: bool = True,
        devId: int | None = None,
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
        if log or self.debug:
            if devId is not None:
                indigo.server.log(
                    f"fetched image from '{indigo.devices[devId].name}' and "
                    f"saving it to: '{save}'"
                )
            else:
                indigo.server.log(f"fetched image: {url} and saving it to: '{save}'")

            self.debug_log(f"fetched image URL: {url}")

        try:
            # Handle authentication type
            if auth_type is None:
                response = requests.get(url, stream=True, timeout=100, verify=False)
            elif auth_type == "basic":
                response = requests.get(
                    url,
                    stream=True,
                    timeout=100,
                    verify=False,
                    auth=HTTPBasicAuth(login, password),
                )
            elif auth_type == "digest":
                response = requests.get(
                    url,
                    stream=True,
                    timeout=100,
                    verify=False,
                    auth=HTTPDigestAuth(login, password),
                )
            else:
                self.logger.error("Unsupported auth type.")
                return False

            # Check response code
            if response.status_code == 200:
                with open(save, "wb") as f:
                    response.raw.decode_content = True
                    shutil.copyfileobj(response.raw, f)
            else:
                self.logger.error(
                    f"error fetching image. Status code: {response.status_code}"
                )
                response.close()
                return False

            response.close()
            return True

        except requests.exceptions.Timeout:
            self.logger.error("the request timed out.")
            return False
        except Exception as e:
            self.logger.error(f"error fetching image. error: {e}")
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
        self, pluginAction: indigo.PluginAction, dev: indigo.Device
    ) -> bool:
        """
        Download multiple camera images, stitch them vertically, and save the result.
        Returns True if successful, False otherwise.
        """
        if not self.configured:
            return False

        start_time: float = time.time()

        # Determine the destination file path
        try:
            if pluginAction.props["useVariable"]:
                destinationFile = indigo.variables[
                    int(pluginAction.props["destinationVariable"])
                ].value
            else:
                destinationFile = self.prepare_text_value(
                    pluginAction.props["destination"]
                )
        except Exception:
            destinationFile = self.prepare_text_value(pluginAction.props["destination"])

        if not destinationFile:
            self.logger.error("Destination file path not provided.")
            return False

        if not os.path.exists(os.path.dirname(destinationFile)):
            self.debug_log(f"Path does not exist: {os.path.dirname(destinationFile)}")
            return False

        # Prepare to gather images
        tempDirectory = os.path.dirname(destinationFile)
        images: list[Image.Image] = []

        # Iterate through up to 10 camera entries
        for i in range(1, 11):
            cam_key = f"cam{i}"
            if cam_key not in pluginAction.props or pluginAction.props[cam_key] in (
                "-1",
                "",
            ):
                self.debug_log("skipping camera")
                continue

            camera_devId = None
            camera_name = ""
            # Find the appropriate camera device
            for camera in indigo.devices.iter(
                filter="org.cynic.indigo.securityspy.camera"
            ):
                if camera.enabled:
                    cameranum = camera.address[
                        camera.address.find("(") + 1 : camera.address.find(")")
                    ]
                    if cameranum == pluginAction.props[cam_key]:
                        camera_devId = camera.id
                        camera_name = camera.name
                        break

            image_url = f"{self.securityspy_url}/++image?cameraNum={pluginAction.props[cam_key]}"
            image_file = os.path.join(tempDirectory, f"temp{i}.jpg")

            # Fetch each camera image
            success = self.get_image(
                url=image_url,
                save=image_file,
                log=True,
                devId=camera_devId,
                auth_type=self.ss_auth_type,
                login=self.securityspy_login,
                password=self.securityspy_pass,
            )
            if not success:
                self.debug_log(
                    f"error obtaining image for camera '{camera_name}', skipping"
                )
                continue

            # Optionally resize the image
            with Image.open(image_file) as img:
                try:
                    if "imageSize" in pluginAction.props and int(
                        pluginAction.props["imageSize"]
                    ):
                        indigo.server.log(
                            f"resized '{camera_name}' camera image "
                            f"to max width of {pluginAction.props['imageSize']}px"
                        )
                        size = (int(pluginAction.props["imageSize"]), 100000)
                        img.thumbnail(size)
                except Exception:
                    pass

                images.append(img.copy())

        # Stitch all retrieved images
        result = self.stitch_images(images)
        result.save(destinationFile)

        # Log results
        end_time: float = time.time()
        total_time: float = round(end_time - start_time, 2)
        file_size_kb: int = os.path.getsize(destinationFile) >> 10
        file_size_str = f"{file_size_kb} KB"
        indigo.server.log(
            f"stitched {len(images)} camera images and saved to: {destinationFile} "
            f"({file_size_str}).  Total time: {total_time} seconds."
        )

        # Clean up temporary files (assuming max 10 used; example cleanup at 1..7)
        for i in range(1, 11):
            temp_path = os.path.join(tempDirectory, f"temp{i}.jpg")
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
                cameraname = camera.name
                cameranum = camera.address[
                    camera.address.find("(") + 1 : camera.address.find(")")
                ]
                filter_list_ui.append((cameranum, cameraname))

        # If no cameras found, create placeholders for up to 16
        if not filter_list_ui:
            for i in range(16):
                filter_list_ui.append((str(i), f"Camera {i}"))

        # Always include the 'none' option
        filter_list_ui.append(("-1", "none"))

        return filter_list_ui

    def download_image_action(
        self, pluginAction: indigo.PluginAction, dev: indigo.Device
    ) -> bool:
        """
        Download a single image (or multiple frames for an animated GIF) from the configured source.
        Returns True on success, False otherwise.
        """
        if not self.configured:
            return False

        start_time: float = time.time()
        hide_log: bool = pluginAction.props.get("hidelog", False)

        # Determine the destination file path
        try:
            if pluginAction.props["useVariable"]:
                destinationFile = indigo.variables[
                    int(pluginAction.props["destinationVariable"])
                ].value
            else:
                destinationFile = self.prepare_text_value(
                    pluginAction.props["destination"]
                )
        except Exception:
            destinationFile = self.prepare_text_value(pluginAction.props["destination"])

        if not destinationFile:
            self.logger.error("Destination file path not provided.")
            return False

        # Validate path
        if not os.path.exists(os.path.dirname(destinationFile)):
            self.logger.error(
                f"path does not exist: {os.path.dirname(destinationFile)}"
            )
            return False

        camera_devId = None
        camera_name = ""
        image_url = ""

        # Handle SecuritySpy camera fetch
        if pluginAction.props["type"] == "securityspy":
            for camera in indigo.devices.iter(
                filter="org.cynic.indigo.securityspy.camera"
            ):
                if camera.enabled:
                    cameranum = camera.address[
                        camera.address.find("(") + 1 : camera.address.find(")")
                    ]
                    if cameranum == pluginAction.props["cam1"]:
                        camera_devId = camera.id
                        camera_name = camera.name
                        break
            image_url = (
                f"{self.securityspy_url}/++image?cameraNum={pluginAction.props['cam1']}"
            )
        else:
            # If not a SecuritySpy camera, we assume a direct URL
            raw_url = pluginAction.props.get("url", "")
            # Convert raw_url if needed
            processed_url = self.prepare_text_value(raw_url) or b""
            image_url = processed_url.decode("utf-8", errors="ignore")

        # Handle resizing
        imageSize: int = -1
        try:
            if (
                "imageSize" in pluginAction.props
                and pluginAction.props["imageSize"]
                and int(pluginAction.props["imageSize"])
            ):
                imageSize = int(pluginAction.props["imageSize"])
        except ValueError:
            self.logger.error("error with the resize, must be an integer.")

        # Determine auth properties
        getImage_auth = self.ss_auth_type
        getImage_login = self.securityspy_login
        getImage_password = self.securityspy_pass
        if pluginAction.props["type"] == "urlType":
            # Possibly override with other auth choices
            if (
                "useAuth" not in pluginAction.props
                or pluginAction.props["useAuth"] == "none"
            ):
                getImage_auth = None
            else:
                getImage_auth = pluginAction.props["useAuth"]
                getImage_login = pluginAction.props.get("login", None)
                getImage_password = pluginAction.props.get("password", None)

        # If not creating an animated GIF
        if not pluginAction.props.get("gif"):
            temp_directory = os.path.dirname(destinationFile)
            if imageSize != -1:
                saveLocation = os.path.join(temp_directory, "temp_forResize.jpg")
            else:
                saveLocation = destinationFile

            try:
                self.get_image(
                    url=image_url,
                    save=saveLocation,
                    log=not hide_log,
                    devId=camera_devId,
                    auth_type=getImage_auth,
                    login=getImage_login,
                    password=getImage_password,
                )
            except Exception:
                indigo.server.log(
                    "error fetching the image, not proceeding with resizing"
                )
                return False

            # If resizing was requested, load, resize, then save
            if imageSize != -1:
                with Image.open(saveLocation) as img:
                    size = (imageSize, 100000)
                    img.thumbnail(size)
                    img.save(destinationFile)
                try:
                    os.remove(saveLocation)
                except Exception:
                    pass

            if not hide_log:
                if pluginAction.props["type"] == "securityspy":
                    indigo.server.log(
                        f"fetched image from '{camera_name}', "
                        f"resized, and saved it to: {destinationFile}"
                    )
                else:
                    indigo.server.log(
                        f"fetched images from '{image_url}', "
                        f"resized, and saved to: {destinationFile}"
                    )

        else:
            # Handle animated GIF creation
            quality: int = 60
            # Ensure file extension is .gif
            if not destinationFile.lower().endswith(".gif"):
                base_path, _ = os.path.splitext(destinationFile)
                destinationFile = base_path + ".gif"

            temp_directory = os.path.dirname(destinationFile)
            filenames: list[str] = []
            i: int = 0

            # Duration for total GIF capture time
            try:
                total_gif_time = int(pluginAction.props.get("gifTime", 4))
            except ValueError:
                total_gif_time = 4

            # Capture frames every 2 seconds, for total_gif_time
            while i * 2.0 <= total_gif_time:
                if i != 0:
                    end_time = time.time()
                    total_time_elapsed = round(end_time - start_time, 2)
                    sleep_time = (2 * i) - total_time_elapsed
                    self.debug_log(
                        f"time since start: {total_time_elapsed}s; "
                        f"sleeping for: {sleep_time}s; next frame: {total_time_elapsed + sleep_time}s."
                    )
                    time.sleep(max(0, sleep_time))

                temp_filename = os.path.join(temp_directory, f"temp_forGif{i}.jpg")
                self.get_image(
                    url=image_url,
                    save=temp_filename,
                    log=not hide_log,
                    devId=camera_devId,
                    auth_type=getImage_auth,
                    login=getImage_login,
                    password=getImage_password,
                )

                # Optionally resize
                with Image.open(temp_filename) as frame_img:
                    if imageSize != -1:
                        size = (imageSize, 100000)
                        frame_img.thumbnail(size)
                    frame_img.save(temp_filename, "JPEG", quality=quality)

                filenames.append(temp_filename)
                i += 1

            # Open each saved frame and store in memory
            images: list[Image.Image] = []
            for fname in filenames:
                with Image.open(fname) as frame:
                    images.append(frame.copy())
                try:
                    os.remove(fname)
                except Exception:
                    pass

            # Save the frames as an animated GIF
            images[0].save(
                destinationFile,
                save_all=True,
                append_images=images[1:],
                duration=300,
                loop=0,
                quality=quality,
            )

            file_size_kb = os.path.getsize(destinationFile) >> 10
            file_size_str = f"{file_size_kb} KB"
            end_time = time.time()
            total_time = round(end_time - start_time, 2)

            if not hide_log:
                if pluginAction.props["type"] == "securityspy":
                    indigo.server.log(
                        f"fetched images from '{camera_name}', created an animated gif "
                        f"({total_gif_time}s, {i} frames), saved to: {destinationFile} "
                        f"({file_size_str}).  Total time: {total_time}s."
                    )
                else:
                    indigo.server.log(
                        f"fetched images from '{image_url}', created an animated gif "
                        f"({total_gif_time}s, {i} frames), saved to: {destinationFile} "
                        f"({file_size_str}).  Total time: {total_time}s."
                    )

        return True
