import datetime
import os
import shutil
import time
from typing import Optional, List, Tuple, Union

import requests
from PIL import Image
from requests.auth import HTTPDigestAuth, HTTPBasicAuth

try:
    import indigo
except ImportError:
    # Allow running in development/test environments without Indigo
    pass

# Configuration constants
DEFAULT_UPDATE_FREQUENCY = 24  # Hours between update checks
REQUEST_TIMEOUT = 30  # Seconds for HTTP requests
GIF_FRAME_INTERVAL = 2.0  # Seconds between GIF frames
MAX_CAMERAS = 10  # Maximum cameras supported for stitching

# Supported SecuritySpy plugin configurations
SECURITYSPY_PLUGINS = {
    'cynical': {
        'filter': 'org.cynic.indigo.securityspy.camera',
        'name': 'Cynical SecuritySpy',
        'address_parser': '_parse_cynical_address',
        'device_type_filter': None  # No device type filtering needed
    },
    'flyingdiver': {
        'filter': 'com.flyingdiver.indigoplugin.securityspy',
        'name': 'Spy Connect', 
        'address_parser': '_parse_flyingdiver_address',
        'device_type_filter': 'spyCamera'  # Only include camera devices, exclude spyServer
    }
}


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
        
        Args:
            plugin_id: Unique identifier for this plugin
            plugin_display_name: Human-readable plugin name
            plugin_version: Version string for this plugin
            plugin_prefs: Dictionary of plugin preferences from Indigo
        """
        super(Plugin, self).__init__(
            plugin_id, plugin_display_name, plugin_version, plugin_prefs
        )

        # SecuritySpy connection configuration
        # These values come from the plugin's configuration dialog
        self.security_spy_ip: Optional[str] = plugin_prefs.get("ip")
        self.security_spy_port: Optional[str] = plugin_prefs.get("port")
        self.security_spy_login: Optional[str] = plugin_prefs.get("login")
        self.security_spy_pass: Optional[str] = plugin_prefs.get("password")
        self.use_ssl: bool = plugin_prefs.get("ssl", False)
        
        # Determine auth type based on whether credentials are provided
        # SecuritySpy typically uses basic auth when credentials are set
        self.security_spy_auth_type: Optional[str] = (
            "basic" if self.security_spy_login else None
        )

        # Plugin lifecycle tracking
        self.last_update_check: Optional[datetime.datetime] = None
        self.plugin_version: str = plugin_version
        
        # Build SecuritySpy base URL and validate configuration
        self._update_connection_url()
        
        self.debug_log("Plugin initialized with SecuritySpy connection settings")

    def debug_log(self, message: str) -> None:
        """
        Log a debug message if debugging is enabled.
        """
        if self.debug:
            self.logger.debug(message)

    def _update_connection_url(self) -> None:
        """
        Construct the base SecuritySpy URL from plugin preferences.
        
        Sets self.configured to indicate whether we have sufficient
        configuration to connect to SecuritySpy. Updates self.security_spy_url
        with the properly formatted base URL.
        """
        # Check if we have minimum required configuration
        self.configured: bool = (
            self.security_spy_ip is not None and 
            self.security_spy_port is not None and
            self.security_spy_ip.strip() != "" and
            self.security_spy_port.strip() != ""
        )
        
        if not self.configured:
            self.security_spy_url = ""
            return
            
        # Build URL with appropriate protocol
        protocol = "https" if self.use_ssl else "http"
        self.security_spy_url = f"{protocol}://{self.security_spy_ip}:{self.security_spy_port}"
        
        self.debug_log(f"SecuritySpy URL configured: {protocol}://{self.security_spy_ip}:{self.security_spy_port}")

    def startup(self) -> None:
        """
        Perform any required logic at plugin startup.
        """
        self.debug_log("Plugin startup called")

    def closedPrefsConfigUi(self, valuesDict: dict, userCancelled: bool) -> None:
        """
        Handle actions after plugin preferences dialog is closed.
        
        This method is called by Indigo when the user closes the plugin
        configuration dialog. We update our internal settings and
        reconstruct the SecuritySpy connection URL.
        
        Args:
            valuesDict: Dictionary containing updated preference values
            userCancelled: True if user cancelled the dialog
        """
        if not userCancelled:
            # Update internal configuration from dialog values
            self.debug = valuesDict.get("debug", False)
            self.security_spy_ip = valuesDict.get("ip", "")
            self.security_spy_port = valuesDict.get("port", "")
            self.security_spy_login = valuesDict.get("login", "")
            self.security_spy_pass = valuesDict.get("password", "")
            self.use_ssl = valuesDict.get("ssl", False)

            # Update auth type based on whether credentials are provided
            # Empty string evaluates to False, so check length explicitly
            self.security_spy_auth_type = (
                "basic" if self.security_spy_login and len(self.security_spy_login.strip()) > 0 
                else None
            )

            # Rebuild the SecuritySpy URL with updated preferences
            self._update_connection_url()
            
            self.debug_log(f"Configuration updated - SecuritySpy configured: {self.configured}")

    def shutdown(self) -> None:
        """
        Handle any required shutdown actions for the plugin.
        """
        self.debug_log("Plugin shutdown called")

    def prepare_text_value(self, input_string: Optional[str]) -> Optional[bytes]:
        """
        Process and encode a text value for use in file operations.
        
        This method handles Indigo variable substitution (%%v:123%% syntax)
        and ensures consistent UTF-8 encoding for file paths and URLs.
        
        Args:
            input_string: Raw string that may contain Indigo variables
            
        Returns:
            UTF-8 encoded bytes, or None if input was None
        """
        if input_string is None:
            return None

        # Remove leading/trailing whitespace
        cleaned_string = input_string.strip()
        
        # Let Indigo substitute any variables (e.g., %%v:123456%%)
        # This allows users to reference Indigo variables in paths/URLs
        cleaned_string = self.substitute(cleaned_string)
        
        return cleaned_string.encode("utf-8")

    def get_image(
        self,
        url: str,
        save: Union[str, bytes],
        auth_type: Optional[str] = None,
        login: Optional[str] = None,
        password: Optional[str] = None,
    ) -> bool:
        """
        Download an image from a URL and save it to the local filesystem.
        
        This method handles the core image download functionality with support
        for HTTP authentication. It uses streaming download to handle large
        images efficiently.
        
        Args:
            url: Complete URL to download the image from
            save: Local file path where the image should be saved
            auth_type: Authentication method ('basic', 'digest', or None)
            login: Username for authentication (if auth_type is set)
            password: Password for authentication (if auth_type is set)
            
        Returns:
            True if download succeeded, False otherwise
        """
        # Normalize save path to string format
        # Handle both string and bytes input for compatibility
        if isinstance(save, bytes):
            try:
                save_path = save.decode("utf-8")
            except UnicodeDecodeError:
                self.logger.error("Invalid file path encoding")
                return False
        else:
            save_path = save

        self.logger.info(f"Downloading image from {url} to: '{save_path}'")
        self.debug_log(f"Image URL: {url}")

        # Configure authentication based on type
        auth = self._create_auth_handler(auth_type, login, password)
        if auth_type and auth is None:
            return False  # Auth configuration failed

        try:
            # Use streaming download for memory efficiency with large images
            # Disable SSL verification as many camera systems use self-signed certs
            response = requests.get(
                url,
                stream=True,
                timeout=REQUEST_TIMEOUT,
                verify=False,  # SecuritySpy often uses self-signed certificates
                auth=auth,
            )
            response.raise_for_status()

            # Stream the image data directly to file to avoid loading into memory
            with open(save_path, "wb") as f:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, f)

            response.close()
            
            # Log file size for debugging
            file_size = os.path.getsize(save_path)
            self.debug_log(f"Downloaded image: {file_size} bytes")
            return True

        except requests.exceptions.HTTPError as e:
            self.logger.error(f"HTTP error downloading image: {e} (Status: {e.response.status_code if e.response else 'unknown'})")
        except requests.exceptions.Timeout:
            self.logger.error(f"Timeout downloading image from {url} (>{REQUEST_TIMEOUT}s)")
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error downloading image: {e}")
        except OSError as e:
            self.logger.error(f"File system error saving image to '{save_path}': {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error downloading image: {e}")

        return False
    
    def _create_auth_handler(self, auth_type: Optional[str], login: Optional[str], password: Optional[str]):
        """
        Create appropriate authentication handler for HTTP requests.
        
        Args:
            auth_type: Type of authentication ('basic', 'digest', or None)
            login: Username for authentication
            password: Password for authentication
            
        Returns:
            Authentication handler object, or None if no auth or error
        """
        if auth_type is None:
            return None
        elif auth_type == "basic":
            if not login or not password:
                self.logger.error("Basic auth requires both login and password")
                return None
            return HTTPBasicAuth(login, password)
        elif auth_type == "digest":
            if not login or not password:
                self.logger.error("Digest auth requires both login and password")
                return None
            return HTTPDigestAuth(login, password)
        else:
            self.logger.error(f"Unsupported authentication type: '{auth_type}'")
            return None

    def stitch_images(self, images: List[Image.Image]) -> Image.Image:
        """
        Combine multiple PIL Image objects vertically into a single image.
        
        This method creates a new image canvas large enough to hold all input
        images stacked vertically, then pastes each image in sequence. The
        resulting image width matches the widest input image.
        
        Args:
            images: List of PIL Image objects to combine
            
        Returns:
            New PIL Image object containing all images stacked vertically
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

        # Iterate through up to MAX_CAMERAS cameras
        # Each camera is referenced as cam1, cam2, etc. in the action properties
        for i in range(1, MAX_CAMERAS + 1):
            cam_key = f"cam{i}"
            cam_prop = plugin_action.props.get(cam_key, "")
            if cam_prop in ("-1", ""):
                self.debug_log("skipping camera")
                continue

            # Locate the camera device using multi-plugin support
            camera_dev_id, camera_name = self._get_camera_info(cam_prop)

            # Extract camera number from camera ID (handle both old and new formats)
            if ':' in cam_prop:
                camera_num = cam_prop.split(':', 1)[1]
            else:
                camera_num = cam_prop

            # Build the URL for this camera
            image_url = f"{self.security_spy_url}/++image?cameraNum={camera_num}"
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
        for i in range(1, MAX_CAMERAS + 1):
            temp_path = os.path.join(temp_directory, f"temp{i}.jpg")
            try:
                os.remove(temp_path)
                self.debug_log(f"deleting file {temp_path}")
            except OSError as e:
                self.debug_log(f"Failed to delete temporary file {temp_path}: {e}")

        return True

    def camera_list_generator(
        self,
        filter: str = "",  # Required by Indigo API
        valuesDict: Optional[dict] = None,  # Required by Indigo API  
        typeId: str = "",  # Required by Indigo API
        targetId: int = 0,  # Required by Indigo API
    ) -> List[Tuple[str, str]]:
        """
        Generate a list of cameras for UI selection dropdowns.
        
        This method is called by Indigo to populate camera selection
        menus in the plugin's action configuration dialogs. It searches
        for enabled SecuritySpy camera devices from all supported plugins
        and returns them formatted for UI display.
        
        Supported plugins:
        - Cynical SecuritySpy Plugin (org.cynic.indigo.securityspy.camera)
        - FlyingDiver SecuritySpy Plugin (com.flyingdiver.indigoplugin.securityspy)
        
        Args:
            filter: Filter string (required by Indigo API, unused)
            valuesDict: Current dialog values (required by Indigo API, unused)
            typeId: Dialog type ID (required by Indigo API, unused) 
            targetId: Target device ID (required by Indigo API, unused)
            
        Returns:
            List of (camera_number, camera_name) tuples for UI display
        """
        camera_options: List[Tuple[str, str]] = []

        # Discover cameras from all supported SecuritySpy plugins
        discovered_cameras = self._discover_cameras()
        
        for camera_num, camera_name, plugin_type in discovered_cameras:
            # Add plugin identifier to camera name for disambiguation
            plugin_name = SECURITYSPY_PLUGINS[plugin_type]['name']
            display_name = f"{camera_name} ({plugin_name})"
            # Create unique ID by combining plugin type and camera number
            unique_camera_id = f"{plugin_type}:{camera_num}"
            camera_options.append((unique_camera_id, display_name))

        # Sort cameras by number for consistent ordering
        def sort_key(option):
            camera_id = option[0]
            if ':' in camera_id:
                # Extract camera number from plugin:number format
                camera_num = camera_id.split(':', 1)[1]
                return int(camera_num) if camera_num.isdigit() else 999
            return int(camera_id) if camera_id.isdigit() else 999
        
        camera_options.sort(key=sort_key)

        # If no cameras found, create numbered placeholders
        # This provides a fallback when no SecuritySpy plugins are installed
        if not camera_options:
            self.debug_log("No SecuritySpy cameras found from any supported plugin, using fallback camera list")
            for i in range(16):
                camera_options.append((str(i), f"Camera {i} (Manual)"))

        # Always include 'none' option for optional camera slots
        camera_options.append(("-1", "none"))

        return camera_options
    
    def _parse_cynical_address(self, camera_address: str) -> Optional[str]:
        """
        Parse camera number from Cynical SecuritySpy plugin address format.
        
        Address format: "Camera Name (camera_number)"
        Example: "Front Door Camera (1)"
        
        Args:
            camera_address: Camera device address string
            
        Returns:
            Camera number string, or None if parsing fails
        """
        open_paren = camera_address.find("(")
        close_paren = camera_address.find(")")
        if open_paren != -1 and close_paren != -1:
            return camera_address[open_paren + 1:close_paren]
        return None
    
    def _parse_flyingdiver_address(self, camera_address: str) -> Optional[str]:
        """
        Parse camera number from FlyingDiver SecuritySpy plugin address format.
        
        Address format: "{server_id}:{camera_number}"
        Example: "server123:01"
        
        Args:
            camera_address: Camera device address string
            
        Returns:
            Camera number string (without zero-padding), or None if parsing fails
        """
        if ":" in camera_address:
            parts = camera_address.split(":", 1)  # Split only on first colon
            if len(parts) == 2 and parts[0] and parts[1]:
                # Remove zero-padding from camera number
                camera_num = parts[1].lstrip('0') or '0'
                return camera_num
        return None
    
    def _discover_cameras(self) -> List[Tuple[str, str, str]]:
        """
        Discover cameras from all supported SecuritySpy plugins.
        
        Returns:
            List of (camera_number, camera_name, plugin_type) tuples
        """
        discovered_cameras = []
        
        for plugin_key, plugin_config in SECURITYSPY_PLUGINS.items():
            try:
                # Search for devices from this plugin
                device_filter = plugin_config['filter']
                parser_method = getattr(self, plugin_config['address_parser'])
                
                for camera in indigo.devices.iter(filter=device_filter):
                    if camera.enabled:
                        # Apply device type filtering if specified
                        device_type_filter = plugin_config.get('device_type_filter')
                        if device_type_filter and hasattr(camera, 'deviceTypeId'):
                            if camera.deviceTypeId != device_type_filter:
                                continue  # Skip devices that don't match the required type
                        
                        camera_num = parser_method(camera.address)
                        if camera_num:
                            discovered_cameras.append((
                                camera_num, 
                                camera.name, 
                                plugin_key
                            ))
                            
                self.debug_log(f"Found {len([c for c in discovered_cameras if c[2] == plugin_key])} cameras from {plugin_config['name']}")
                
            except Exception as e:
                self.debug_log(f"Error discovering cameras from {plugin_config['name']}: {e}")
        
        return discovered_cameras
    
    def _get_destination_path(self, plugin_action: indigo.PluginAction) -> Optional[str]:
        """
        Extract and validate the destination file path from action properties.
        
        Args:
            plugin_action: Indigo action containing destination configuration
            
        Returns:
            Validated destination file path, or None if invalid
        """
        try:
            if plugin_action.props.get("useVariable", False):
                # Get path from Indigo variable
                var_id = int(plugin_action.props["destinationVariable"])
                destination_file = indigo.variables[var_id].value
            else:
                # Get path directly from action properties
                destination_bytes = self.prepare_text_value(
                    plugin_action.props.get("destination", "")
                )
                destination_file = destination_bytes.decode("utf-8") if destination_bytes else None
        except (KeyError, ValueError, AttributeError) as e:
            self.debug_log(f"Error getting destination from variable, falling back to direct path: {e}")
            destination_bytes = self.prepare_text_value(
                plugin_action.props.get("destination", "")
            )
            destination_file = destination_bytes.decode("utf-8") if destination_bytes else None

        if not destination_file or not destination_file.strip():
            self.logger.error("Destination file path not provided")
            return None

        # Validate that destination directory exists
        dest_dir = os.path.dirname(destination_file)
        if not os.path.exists(dest_dir):
            self.logger.error(f"Destination directory does not exist: {dest_dir}")
            return None
            
        return destination_file
    
    def _get_camera_info(self, camera_id: str) -> Tuple[Optional[int], str]:
        """
        Find camera device information by camera ID.
        
        Args:
            camera_id: Camera ID in format "plugin_type:camera_num" or just "camera_num" for backwards compatibility
            
        Returns:
            Tuple of (camera_device_id, camera_name)
        """
        # Parse camera ID - handle both new format (plugin:number) and old format (just number)
        if ':' in camera_id:
            plugin_type, camera_num = camera_id.split(':', 1)
            # Search only in the specified plugin
            target_plugins = {plugin_type: SECURITYSPY_PLUGINS[plugin_type]} if plugin_type in SECURITYSPY_PLUGINS else {}
        else:
            # Legacy format - search all plugins
            camera_num = camera_id
            target_plugins = SECURITYSPY_PLUGINS
        
        for plugin_key, plugin_config in target_plugins.items():
            try:
                device_filter = plugin_config['filter']
                parser_method = getattr(self, plugin_config['address_parser'])
                
                for camera in indigo.devices.iter(filter=device_filter):
                    if camera.enabled:
                        # Apply device type filtering if specified
                        device_type_filter = plugin_config.get('device_type_filter')
                        if device_type_filter and hasattr(camera, 'deviceTypeId'):
                            if camera.deviceTypeId != device_type_filter:
                                continue  # Skip devices that don't match the required type
                        
                        device_cam_num = parser_method(camera.address)
                        if device_cam_num == camera_num:
                            return camera.id, camera.name
                            
            except Exception as e:
                self.debug_log(f"Error searching for camera {camera_num} in {plugin_config['name']}: {e}")
        
        return None, ""
    
    def _build_image_url(self, plugin_action: indigo.PluginAction) -> Tuple[str, str]:
        """
        Build the image URL based on action configuration.
        
        Args:
            plugin_action: Indigo action containing URL configuration
            
        Returns:
            Tuple of (image_url, camera_name_for_logging)
        """
        if plugin_action.props.get("type") == "securityspy":
            # SecuritySpy camera image
            camera_id = plugin_action.props.get("cam1", "0")
            _, camera_name = self._get_camera_info(camera_id)
            
            # Extract camera number from camera ID (handle both old and new formats)
            if ':' in camera_id:
                camera_num = camera_id.split(':', 1)[1]
            else:
                camera_num = camera_id
                
            image_url = f"{self.security_spy_url}/++image?cameraNum={camera_num}"
            return image_url, camera_name
        else:
            # Direct URL image
            raw_url = plugin_action.props.get("url", "")
            url_bytes = self.prepare_text_value(raw_url) or b""
            image_url = url_bytes.decode("utf-8", errors="ignore")
            return image_url, ""  # No camera name for direct URLs

    def download_image_action(
        self, plugin_action: indigo.PluginAction, dev: indigo.Device
    ) -> bool:
        """
        Download a single image or create an animated GIF from the configured source.
        
        This is the main entry point for the download image action. It handles
        both single image downloads and animated GIF creation based on the
        action configuration.
        
        Args:
            plugin_action: Indigo action containing download configuration
            dev: Indigo device (unused but required by Indigo API)
            
        Returns:
            True if download/creation succeeded, False otherwise
        """
        if not self.configured:
            self.logger.error("Plugin not configured - check SecuritySpy connection settings")
            return False

        start_time = time.time()
        hide_log = plugin_action.props.get("hidelog", False)

        # Get and validate destination path
        destination_file = self._get_destination_path(plugin_action)
        if not destination_file:
            return False

        # Build image URL and get camera info
        image_url, camera_name = self._build_image_url(plugin_action)
        if not image_url:
            self.logger.error("Unable to determine image URL")
            return False

        # Parse optional image resizing parameter
        image_size = self._get_image_size(plugin_action)
        
        # Determine authentication method
        auth_type, login, password = self._get_auth_config(plugin_action)
        
        # Route to appropriate handler based on output type
        if plugin_action.props.get("gif", False):
            return self._create_animated_gif(
                plugin_action, destination_file, image_url, camera_name,
                auth_type, login, password, image_size, start_time, hide_log
            )
        else:
            return self._download_single_image(
                destination_file, image_url, camera_name,
                auth_type, login, password, image_size, hide_log
            )
    
    def _get_image_size(self, plugin_action: indigo.PluginAction) -> int:
        """
        Parse the image size configuration from action properties.
        
        Args:
            plugin_action: Indigo action containing size configuration
            
        Returns:
            Maximum image width in pixels, or -1 if no resizing requested
        """
        try:
            size_prop = plugin_action.props.get("imageSize", "")
            if size_prop and size_prop.strip():
                return int(size_prop)
        except ValueError:
            self.logger.error("Image size must be an integer, ignoring resize option")
        return -1
    
    def _get_auth_config(self, plugin_action: indigo.PluginAction) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Determine authentication configuration for image download.
        
        Args:
            plugin_action: Indigo action containing auth configuration
            
        Returns:
            Tuple of (auth_type, login, password)
        """
        if plugin_action.props.get("type") == "urlType":
            # Custom URL with optional auth override
            use_auth = plugin_action.props.get("useAuth")
            if use_auth in (None, "none"):
                return None, None, None
            else:
                return (
                    use_auth,
                    plugin_action.props.get("login"),
                    plugin_action.props.get("password")
                )
        else:
            # SecuritySpy - use plugin's configured auth
            return self.security_spy_auth_type, self.security_spy_login, self.security_spy_pass

    def _resize_image_if_needed(self, img_path: str, final_path: str, max_width: int) -> None:
        """
        Resize an image file if width limit is specified.
        
        Args:
            img_path: Path to source image file
            final_path: Path where resized image should be saved
            max_width: Maximum width in pixels, or -1 for no resizing
        """
        try:
            with Image.open(img_path) as img:
                if max_width > 0:
                    # Maintain aspect ratio while limiting width
                    img.thumbnail((max_width, 100000), Image.Resampling.LANCZOS)
                img.save(final_path)
        except Exception as e:
            self.logger.error(f"Error resizing image: {e}")
            raise
    
    def _download_single_image(
        self, 
        destination_file: str,
        image_url: str, 
        camera_name: str,
        auth_type: Optional[str],
        login: Optional[str], 
        password: Optional[str],
        image_size: int,
        hide_log: bool
    ) -> bool:
        """
        Download a single image with optional resizing.
        
        Args:
            destination_file: Where to save the final image
            image_url: URL to download from
            camera_name: Camera name for logging (may be empty)
            auth_type: Authentication type for download
            login: Username for authentication
            password: Password for authentication  
            image_size: Maximum width for resizing, or -1 for no resize
            hide_log: Whether to suppress success logging
            
        Returns:
            True if download succeeded, False otherwise
        """
        temp_directory = os.path.dirname(destination_file)
        
        # Save directly if no resizing needed, otherwise use temp file
        if image_size > 0:
            temp_path = os.path.join(temp_directory, "temp_forResize.jpg")
        else:
            temp_path = destination_file

        # Download the image
        success = self.get_image(
            url=image_url,
            save=temp_path,
            auth_type=auth_type,
            login=login,
            password=password,
        )
        
        if not success:
            self.logger.error("Failed to download image")
            return False

        # Handle resizing if requested
        if image_size > 0 and os.path.exists(temp_path):
            try:
                self._resize_image_if_needed(temp_path, destination_file, image_size)
                # Clean up temp file
                os.remove(temp_path)
            except Exception as e:
                self.logger.error(f"Failed to resize image: {e}")
                return False

        # Log success if not hidden
        if not hide_log:
            source_desc = f"'{camera_name}'" if camera_name else f"'{image_url}'"
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
        hide_log: bool
    ) -> bool:
        """
        Create an animated GIF by capturing multiple frames over time.
        
        Args:
            plugin_action: Indigo action containing GIF configuration
            destination_file: Where to save the final GIF
            image_url: URL to capture frames from
            camera_name: Camera name for logging
            auth_type: Authentication type
            login: Username for authentication
            password: Password for authentication
            image_size: Maximum width for frame resizing
            start_time: When the action started (for timing)
            hide_log: Whether to suppress logging
            
        Returns:
            True if GIF creation succeeded, False otherwise
        """
        # Ensure GIF file extension
        if isinstance(destination_file, bytes):
            destination_file = destination_file.decode("utf-8")
        if not destination_file.lower().endswith(".gif"):
            base_path, _ = os.path.splitext(destination_file)
            destination_file = base_path + ".gif"

        temp_directory = os.path.dirname(destination_file)
        frame_files: List[str] = []
        
        # Determine capture duration
        try:
            total_gif_time = int(plugin_action.props.get("gifTime", 4))
        except ValueError:
            total_gif_time = 4
            
        # Capture frames at intervals
        frame_index = 0
        while frame_index * GIF_FRAME_INTERVAL <= total_gif_time:
            if frame_index > 0:
                # Wait for next frame interval
                elapsed = time.time() - start_time
                sleep_time = (GIF_FRAME_INTERVAL * frame_index) - elapsed
                if sleep_time > 0:
                    self.debug_log(f"Waiting {sleep_time:.1f}s for next frame")
                    time.sleep(sleep_time)

            # Capture frame
            frame_filename = os.path.join(temp_directory, f"temp_forGif{frame_index}.jpg")
            success = self.get_image(
                url=image_url,
                save=frame_filename,
                auth_type=auth_type,
                login=login,
                password=password,
            )
            
            if success:
                # Resize frame if needed
                if image_size > 0:
                    try:
                        self._resize_image_if_needed(frame_filename, frame_filename, image_size)
                    except Exception:
                        self.debug_log(f"Failed to resize frame {frame_index}")
                        
                frame_files.append(frame_filename)
            else:
                self.debug_log(f"Failed to capture frame {frame_index}")
                
            frame_index += 1

        # Load frames and create GIF
        frames: List[Image.Image] = []
        for frame_file in frame_files:
            try:
                with Image.open(frame_file) as img:
                    frames.append(img.copy())
            except Exception as e:
                self.debug_log(f"Failed to load frame {frame_file}: {e}")
            
            # Clean up frame file
            try:
                os.remove(frame_file)
            except Exception:
                pass

        if not frames:
            self.logger.error("No frames captured; cannot create GIF")
            return False

        # Apply frame reversal if requested
        if plugin_action.props.get("reverseFrames", False):
            frames.reverse()
            self.logger.info("Reversed frames order for animated GIF")
            
        # Save as animated GIF
        try:
            frames[0].save(
                destination_file,
                save_all=True,
                append_images=frames[1:],
                duration=300,  # 300ms per frame
                loop=0,  # Infinite loop
                quality=60,
            )
        except Exception as e:
            self.logger.error(f"Failed to create animated GIF: {e}")
            return False

        # Log completion
        if not hide_log:
            file_size_kb = os.path.getsize(destination_file) >> 10
            elapsed = time.time() - start_time
            source_desc = f"'{camera_name}'" if camera_name else f"'{image_url}'"
            self.logger.info(
                f"Created animated GIF from {source_desc} "
                f"({total_gif_time}s, {len(frames)} frames) saved to: {destination_file} "
                f"({file_size_kb} KB). Total time: {elapsed:.1f}s"
            )
            
        return True

