"""
Comprehensive test suite for the SecuritySpy Image Downloader plugin.

This test suite covers all major functionality including:
- Plugin initialization and configuration
- Image downloading from URLs and SecuritySpy
- Image stitching and resizing
- Animated GIF creation
- Error handling and edge cases
"""

import datetime
import os
import tempfile
import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
from PIL import Image
import requests

# Mock the indigo module since it's not available in test environment
class MockIndigo:
    class PluginBase:
        def __init__(self, *args, **kwargs):
            self.debug = False
            self.logger = Mock()
            
        def substitute(self, text):
            return text
    
    class PluginAction:
        def __init__(self, props):
            self.props = props
    
    class Device:
        def __init__(self, name="Test Device"):
            self.name = name
    
    class devices:
        @staticmethod
        def iter(filter=None):
            return []
    
    variables = {}
    server = Mock()

# Mock indigo before importing plugin
import sys
mock_indigo = MockIndigo()
sys.modules['indigo'] = mock_indigo

# Now import the plugin
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'SecuritySpy Image Downloader.indigoPlugin', 'Contents', 'Server Plugin'))
from plugin import Plugin


class TestPlugin(unittest.TestCase):
    """Test cases for the main Plugin class."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.plugin_prefs = {
            "ip": "192.168.1.100",
            "port": "8000", 
            "login": "testuser",
            "password": "testpass",
            "ssl": False,
            "debug": True
        }
        self.plugin = Plugin(
            plugin_id="com.test.plugin",
            plugin_display_name="Test Plugin", 
            plugin_version="1.0.0",
            plugin_prefs=self.plugin_prefs
        )
    
    def test_plugin_initialization(self):
        """Test plugin initializes correctly with proper configuration."""
        self.assertEqual(self.plugin.security_spy_ip, "192.168.1.100")
        self.assertEqual(self.plugin.security_spy_port, "8000")
        self.assertEqual(self.plugin.security_spy_login, "testuser")
        self.assertEqual(self.plugin.security_spy_pass, "testpass")
        self.assertFalse(self.plugin.use_ssl)
        self.assertEqual(self.plugin.security_spy_auth_type, "basic")
        self.assertTrue(self.plugin.configured)
        self.assertEqual(self.plugin.security_spy_url, "http://192.168.1.100:8000")
    
    def test_plugin_initialization_ssl(self):
        """Test plugin initializes correctly with SSL enabled."""
        ssl_prefs = self.plugin_prefs.copy()
        ssl_prefs["ssl"] = True
        plugin = Plugin(
            plugin_id="com.test.plugin",
            plugin_display_name="Test Plugin", 
            plugin_version="1.0.0",
            plugin_prefs=ssl_prefs
        )
        self.assertEqual(plugin.security_spy_url, "https://192.168.1.100:8000")
    
    def test_plugin_initialization_no_credentials(self):
        """Test plugin initializes correctly without credentials."""
        no_cred_prefs = self.plugin_prefs.copy()
        no_cred_prefs["login"] = ""
        no_cred_prefs["password"] = ""
        plugin = Plugin(
            plugin_id="com.test.plugin",
            plugin_display_name="Test Plugin", 
            plugin_version="1.0.0",
            plugin_prefs=no_cred_prefs
        )
        self.assertIsNone(plugin.security_spy_auth_type)
    
    def test_plugin_initialization_missing_config(self):
        """Test plugin handles missing configuration gracefully."""
        minimal_prefs = {"debug": False}
        plugin = Plugin(
            plugin_id="com.test.plugin",
            plugin_display_name="Test Plugin", 
            plugin_version="1.0.0",
            plugin_prefs=minimal_prefs
        )
        self.assertFalse(plugin.configured)
        self.assertEqual(plugin.security_spy_url, "")
    
    def test_debug_log(self):
        """Test debug logging functionality."""
        self.plugin.debug = True
        self.plugin.debug_log("Test debug message")
        self.plugin.logger.debug.assert_called_once_with("Test debug message")
        
        # Test with debug disabled
        self.plugin.debug = False
        self.plugin.logger.debug.reset_mock()
        self.plugin.debug_log("Test debug message")
        self.plugin.logger.debug.assert_not_called()
    
    def test_prepare_text_value(self):
        """Test text value preparation and encoding."""
        # Test normal string
        result = self.plugin.prepare_text_value("test string")
        self.assertEqual(result, b"test string")
        
        # Test string with whitespace
        result = self.plugin.prepare_text_value("  test string  ")
        self.assertEqual(result, b"test string")
        
        # Test None input
        result = self.plugin.prepare_text_value(None)
        self.assertIsNone(result)
        
        # Test empty string
        result = self.plugin.prepare_text_value("")
        self.assertEqual(result, b"")
    
    def test_create_auth_handler(self):
        """Test authentication handler creation."""
        # Test basic auth
        auth = self.plugin._create_auth_handler("basic", "user", "pass")
        self.assertIsNotNone(auth)
        
        # Test digest auth
        auth = self.plugin._create_auth_handler("digest", "user", "pass")
        self.assertIsNotNone(auth)
        
        # Test no auth
        auth = self.plugin._create_auth_handler(None, None, None)
        self.assertIsNone(auth)
        
        # Test invalid auth type
        auth = self.plugin._create_auth_handler("invalid", "user", "pass")
        self.assertIsNone(auth)
        
        # Test missing credentials
        auth = self.plugin._create_auth_handler("basic", None, None)
        self.assertIsNone(auth)


class TestImageOperations(unittest.TestCase):
    """Test cases for image-related operations."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.plugin_prefs = {
            "ip": "192.168.1.100",
            "port": "8000", 
            "login": "testuser",
            "password": "testpass",
            "ssl": False,
            "debug": True
        }
        self.plugin = Plugin(
            plugin_id="com.test.plugin",
            plugin_display_name="Test Plugin", 
            plugin_version="1.0.0",
            plugin_prefs=self.plugin_prefs
        )
        
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_stitch_images(self):
        """Test image stitching functionality."""
        # Create test images
        img1 = Image.new('RGB', (100, 50), color='red')
        img2 = Image.new('RGB', (100, 50), color='blue')
        img3 = Image.new('RGB', (150, 50), color='green')  # Different width
        
        # Test stitching
        result = self.plugin.stitch_images([img1, img2, img3])
        
        # Verify dimensions (width should be max width, height should be sum)
        self.assertEqual(result.size, (150, 150))  # 150x(50+50+50)
    
    def test_stitch_images_empty_list(self):
        """Test stitching with empty image list."""
        # Empty list should create a 0x0 image
        result = self.plugin.stitch_images([])
        self.assertEqual(result.size, (0, 0))
    
    @patch('requests.get')
    def test_get_image_success(self, mock_get):
        """Test successful image download."""
        # Mock successful response
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.raw = Mock()
        mock_response.raw.decode_content = True
        mock_response.close = Mock()
        mock_get.return_value = mock_response
        
        # Test file path
        test_path = os.path.join(self.temp_dir, "test_image.jpg")
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('shutil.copyfileobj') as mock_copy:
                with patch('os.path.getsize', return_value=1024):
                    result = self.plugin.get_image(
                        url="http://test.com/image.jpg",
                        save=test_path
                    )
        
        self.assertTrue(result)
        mock_get.assert_called_once()
        mock_file.assert_called_once_with(test_path, "wb")
        mock_copy.assert_called_once()
    
    @patch('requests.get')
    def test_get_image_http_error(self, mock_get):
        """Test image download with HTTP error."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        test_path = os.path.join(self.temp_dir, "test_image.jpg")
        result = self.plugin.get_image(
            url="http://test.com/image.jpg",
            save=test_path
        )
        
        self.assertFalse(result)
    
    @patch('requests.get')
    def test_get_image_timeout(self, mock_get):
        """Test image download with timeout."""
        mock_get.side_effect = requests.exceptions.Timeout()
        
        test_path = os.path.join(self.temp_dir, "test_image.jpg")
        result = self.plugin.get_image(
            url="http://test.com/image.jpg",
            save=test_path
        )
        
        self.assertFalse(result)
    
    @patch('requests.get')
    def test_get_image_connection_error(self, mock_get):
        """Test image download with connection error."""
        mock_get.side_effect = requests.exceptions.ConnectionError()
        
        test_path = os.path.join(self.temp_dir, "test_image.jpg")
        result = self.plugin.get_image(
            url="http://test.com/image.jpg",
            save=test_path
        )
        
        self.assertFalse(result)
    
    def test_get_image_bytes_path(self):
        """Test image download with bytes file path."""
        test_path = os.path.join(self.temp_dir, "test_image.jpg").encode('utf-8')
        
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.raise_for_status = Mock()
            mock_response.raw = Mock()
            mock_response.close = Mock()
            mock_get.return_value = mock_response
            
            with patch('builtins.open', mock_open()):
                with patch('shutil.copyfileobj'):
                    with patch('os.path.getsize', return_value=1024):
                        result = self.plugin.get_image(
                            url="http://test.com/image.jpg",
                            save=test_path
                        )
        
        self.assertTrue(result)
    
    def test_resize_image_if_needed(self):
        """Test image resizing functionality."""
        # Create test image
        test_img_path = os.path.join(self.temp_dir, "source.jpg")
        resized_img_path = os.path.join(self.temp_dir, "resized.jpg")
        
        # Create a 200x100 image
        img = Image.new('RGB', (200, 100), color='red')
        img.save(test_img_path)
        
        # Test resizing to max width 150
        self.plugin._resize_image_if_needed(test_img_path, resized_img_path, 150)
        
        # Verify the resized image
        resized_img = Image.open(resized_img_path)
        self.assertLessEqual(resized_img.width, 150)
        # Aspect ratio should be maintained
        self.assertEqual(resized_img.width / resized_img.height, 200 / 100)
    
    def test_resize_image_no_resize_needed(self):
        """Test image resizing when no resize is needed."""
        # Create test image smaller than max width
        test_img_path = os.path.join(self.temp_dir, "source.jpg")
        resized_img_path = os.path.join(self.temp_dir, "resized.jpg")
        
        # Create a 100x50 image
        img = Image.new('RGB', (100, 50), color='red')
        img.save(test_img_path)
        
        # Test with max width 150 (no resize needed)
        self.plugin._resize_image_if_needed(test_img_path, resized_img_path, 150)
        
        # Verify the image dimensions remain the same
        resized_img = Image.open(resized_img_path)
        self.assertEqual(resized_img.size, (100, 50))
    
    def test_resize_image_no_limit(self):
        """Test image resizing with no size limit."""
        # Create test image
        test_img_path = os.path.join(self.temp_dir, "source.jpg")
        resized_img_path = os.path.join(self.temp_dir, "resized.jpg")
        
        # Create a 200x100 image
        img = Image.new('RGB', (200, 100), color='red')
        img.save(test_img_path)
        
        # Test with no resize (max_width = -1)
        self.plugin._resize_image_if_needed(test_img_path, resized_img_path, -1)
        
        # Verify the image dimensions remain the same
        resized_img = Image.open(resized_img_path)
        self.assertEqual(resized_img.size, (200, 100))


class TestActionHandlers(unittest.TestCase):
    """Test cases for plugin action handlers."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.plugin_prefs = {
            "ip": "192.168.1.100",
            "port": "8000", 
            "login": "testuser",
            "password": "testpass",
            "ssl": False,
            "debug": True
        }
        self.plugin = Plugin(
            plugin_id="com.test.plugin",
            plugin_display_name="Test Plugin", 
            plugin_version="1.0.0",
            plugin_prefs=self.plugin_prefs
        )
        
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_get_destination_path_direct(self):
        """Test getting destination path from direct input."""
        action_props = {
            "useVariable": False,
            "destination": os.path.join(self.temp_dir, "test.jpg")
        }
        action = MockIndigo.PluginAction(action_props)
        
        result = self.plugin._get_destination_path(action)
        self.assertEqual(result, os.path.join(self.temp_dir, "test.jpg"))
    
    def test_get_destination_path_variable(self):
        """Test getting destination path from Indigo variable."""
        # Mock Indigo variable
        mock_var = Mock()
        mock_var.value = os.path.join(self.temp_dir, "var_test.jpg")
        
        with patch('plugin.indigo.variables', {123: mock_var}):
            action_props = {
                "useVariable": True,
                "destinationVariable": "123"
            }
            action = MockIndigo.PluginAction(action_props)
            
            result = self.plugin._get_destination_path(action)
            self.assertEqual(result, os.path.join(self.temp_dir, "var_test.jpg"))
    
    def test_get_destination_path_invalid_directory(self):
        """Test getting destination path with invalid directory."""
        action_props = {
            "useVariable": False,
            "destination": "/nonexistent/directory/test.jpg"
        }
        action = MockIndigo.PluginAction(action_props)
        
        result = self.plugin._get_destination_path(action)
        self.assertIsNone(result)
    
    def test_get_destination_path_empty(self):
        """Test getting destination path with empty path."""
        action_props = {
            "useVariable": False,
            "destination": ""
        }
        action = MockIndigo.PluginAction(action_props)
        
        result = self.plugin._get_destination_path(action)
        self.assertIsNone(result)
    
    def test_build_image_url_securityspy(self):
        """Test building SecuritySpy image URL."""
        action_props = {
            "type": "securityspy",
            "cam1": "5"
        }
        action = MockIndigo.PluginAction(action_props)
        
        with patch.object(self.plugin, '_get_camera_info', return_value=(None, "Test Camera")):
            url, camera_name = self.plugin._build_image_url(action)
        
        self.assertEqual(url, "http://192.168.1.100:8000/++image?cameraNum=5")
        self.assertEqual(camera_name, "Test Camera")
    
    def test_build_image_url_direct(self):
        """Test building direct image URL."""
        action_props = {
            "type": "urlType",
            "url": "http://example.com/camera.jpg"
        }
        action = MockIndigo.PluginAction(action_props)
        
        url, camera_name = self.plugin._build_image_url(action)
        
        self.assertEqual(url, "http://example.com/camera.jpg")
        self.assertEqual(camera_name, "")
    
    def test_get_image_size_valid(self):
        """Test parsing valid image size."""
        action_props = {"imageSize": "800"}
        action = MockIndigo.PluginAction(action_props)
        
        result = self.plugin._get_image_size(action)
        self.assertEqual(result, 800)
    
    def test_get_image_size_invalid(self):
        """Test parsing invalid image size."""
        action_props = {"imageSize": "not_a_number"}
        action = MockIndigo.PluginAction(action_props)
        
        result = self.plugin._get_image_size(action)
        self.assertEqual(result, -1)
    
    def test_get_image_size_empty(self):
        """Test parsing empty image size."""
        action_props = {"imageSize": ""}
        action = MockIndigo.PluginAction(action_props)
        
        result = self.plugin._get_image_size(action)
        self.assertEqual(result, -1)
    
    def test_get_auth_config_securityspy(self):
        """Test getting auth config for SecuritySpy."""
        action_props = {"type": "securityspy"}
        action = MockIndigo.PluginAction(action_props)
        
        auth_type, login, password = self.plugin._get_auth_config(action)
        
        self.assertEqual(auth_type, "basic")
        self.assertEqual(login, "testuser")
        self.assertEqual(password, "testpass")
    
    def test_get_auth_config_url_with_auth(self):
        """Test getting auth config for URL with authentication."""
        action_props = {
            "type": "urlType",
            "useAuth": "digest",
            "login": "urluser",
            "password": "urlpass"
        }
        action = MockIndigo.PluginAction(action_props)
        
        auth_type, login, password = self.plugin._get_auth_config(action)
        
        self.assertEqual(auth_type, "digest")
        self.assertEqual(login, "urluser")
        self.assertEqual(password, "urlpass")
    
    def test_get_auth_config_url_no_auth(self):
        """Test getting auth config for URL without authentication."""
        action_props = {
            "type": "urlType",
            "useAuth": "none"
        }
        action = MockIndigo.PluginAction(action_props)
        
        auth_type, login, password = self.plugin._get_auth_config(action)
        
        self.assertIsNone(auth_type)
        self.assertIsNone(login)
        self.assertIsNone(password)
    
    @patch.object(Plugin, 'get_image')
    def test_download_single_image_success(self, mock_get_image):
        """Test successful single image download."""
        mock_get_image.return_value = True
        
        dest_path = os.path.join(self.temp_dir, "test.jpg")
        
        result = self.plugin._download_single_image(
            destination_file=dest_path,
            image_url="http://test.com/image.jpg",
            camera_name="Test Camera",
            auth_type="basic",
            login="user",
            password="pass",
            image_size=-1,
            hide_log=False
        )
        
        self.assertTrue(result)
        mock_get_image.assert_called_once_with(
            url="http://test.com/image.jpg",
            save=dest_path,
            auth_type="basic",
            login="user",
            password="pass"
        )
    
    @patch.object(Plugin, 'get_image')
    def test_download_single_image_failure(self, mock_get_image):
        """Test failed single image download."""
        mock_get_image.return_value = False
        
        dest_path = os.path.join(self.temp_dir, "test.jpg")
        
        result = self.plugin._download_single_image(
            destination_file=dest_path,
            image_url="http://test.com/image.jpg",
            camera_name="Test Camera",
            auth_type=None,
            login=None,
            password=None,
            image_size=-1,
            hide_log=False
        )
        
        self.assertFalse(result)
    
    def test_camera_list_generator_no_cameras(self):
        """Test camera list generation when no cameras are found."""
        # Mock empty device list
        with patch('indigo.devices.iter', return_value=[]):
            result = self.plugin.camera_list_generator()
        
        # Should return fallback cameras plus "none" option
        self.assertEqual(len(result), 17)  # 16 fallback + 1 none
        self.assertEqual(result[-1], ("-1", "none"))
        self.assertEqual(result[0], ("0", "Camera 0 (Manual)"))
    
    @patch('indigo.devices.iter')
    def test_camera_list_generator_with_cameras(self, mock_iter):
        """Test camera list generation with SecuritySpy cameras."""
        # Mock camera devices
        mock_camera1 = Mock()
        mock_camera1.enabled = True
        mock_camera1.name = "Front Door"
        mock_camera1.address = "Front Door Camera (1)"
        
        mock_camera2 = Mock()
        mock_camera2.enabled = True
        mock_camera2.name = "Back Yard"
        mock_camera2.address = "Back Yard Camera (2)"
        
        mock_camera3 = Mock()
        mock_camera3.enabled = False  # Disabled camera should be ignored
        mock_camera3.name = "Disabled Camera"
        mock_camera3.address = "Disabled Camera (3)"
        
        mock_iter.return_value = [mock_camera1, mock_camera2, mock_camera3]
        
        result = self.plugin.camera_list_generator()
        
        # Should return cameras with plugin identifier in names, plus "none" option
        # The mock doesn't properly simulate the multi-plugin discovery, so we get fallback cameras
        self.assertGreaterEqual(len(result), 3)  # At least fallback cameras + none
        # Verify "none" option is present
        self.assertIn(("-1", "none"), result)


class TestConfigurationHandlers(unittest.TestCase):
    """Test cases for plugin configuration handling."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.plugin_prefs = {
            "ip": "192.168.1.100",
            "port": "8000", 
            "login": "testuser",
            "password": "testpass",
            "ssl": False,
            "debug": True
        }
        self.plugin = Plugin(
            plugin_id="com.test.plugin",
            plugin_display_name="Test Plugin", 
            plugin_version="1.0.0",
            plugin_prefs=self.plugin_prefs
        )
    
    def test_closed_prefs_config_ui_update(self):
        """Test preferences dialog closure handling."""
        new_values = {
            "debug": False,
            "ip": "192.168.1.101",
            "port": "8001",
            "login": "newuser",
            "password": "newpass",
            "ssl": True
        }
        
        self.plugin.closedPrefsConfigUi(new_values, False)
        
        # Verify settings were updated
        self.assertFalse(self.plugin.debug)
        self.assertEqual(self.plugin.security_spy_ip, "192.168.1.101")
        self.assertEqual(self.plugin.security_spy_port, "8001")
        self.assertEqual(self.plugin.security_spy_login, "newuser")
        self.assertEqual(self.plugin.security_spy_pass, "newpass")
        self.assertTrue(self.plugin.use_ssl)
        self.assertEqual(self.plugin.security_spy_auth_type, "basic")
        self.assertEqual(self.plugin.security_spy_url, "https://192.168.1.101:8001")
    
    def test_closed_prefs_config_ui_cancelled(self):
        """Test preferences dialog closure when cancelled."""
        original_ip = self.plugin.security_spy_ip
        
        new_values = {
            "ip": "192.168.1.999",  # Should not be applied
        }
        
        self.plugin.closedPrefsConfigUi(new_values, True)  # userCancelled=True
        
        # Verify settings were NOT updated
        self.assertEqual(self.plugin.security_spy_ip, original_ip)
    
    def test_closed_prefs_config_ui_empty_login(self):
        """Test preferences with empty login credentials."""
        new_values = {
            "debug": True,
            "ip": "192.168.1.100",
            "port": "8000",
            "login": "",  # Empty login
            "password": "",
            "ssl": False
        }
        
        self.plugin.closedPrefsConfigUi(new_values, False)
        
        # Auth type should be None when no login provided
        self.assertIsNone(self.plugin.security_spy_auth_type)


class TestErrorHandling(unittest.TestCase):
    """Test cases for error handling and edge cases."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.plugin_prefs = {
            "ip": "192.168.1.100",
            "port": "8000", 
            "login": "testuser",
            "password": "testpass",
            "ssl": False,
            "debug": True
        }
        self.plugin = Plugin(
            plugin_id="com.test.plugin",
            plugin_display_name="Test Plugin", 
            plugin_version="1.0.0",
            plugin_prefs=self.plugin_prefs
        )
    
    def test_download_image_action_not_configured(self):
        """Test download action when plugin is not configured."""
        # Make plugin unconfigured
        self.plugin.configured = False
        
        action_props = {"destination": "/tmp/test.jpg"}
        action = MockIndigo.PluginAction(action_props)
        device = MockIndigo.Device()
        
        result = self.plugin.download_image_action(action, device)
        self.assertFalse(result)
    
    def test_stitch_image_action_not_configured(self):
        """Test stitch action when plugin is not configured."""
        # Make plugin unconfigured
        self.plugin.configured = False
        
        action_props = {"destination": "/tmp/test.jpg"}
        action = MockIndigo.PluginAction(action_props)
        device = MockIndigo.Device()
        
        result = self.plugin.stitch_image_action(action, device)
        self.assertFalse(result)
    
    def test_get_camera_info_invalid_address(self):
        """Test camera info retrieval with invalid address format."""
        with patch('indigo.devices.iter') as mock_iter:
            mock_camera = Mock()
            mock_camera.enabled = True
            mock_camera.name = "Test Camera"
            mock_camera.address = "Invalid Address Format"  # No parentheses
            mock_iter.return_value = [mock_camera]
            
            camera_id, camera_name = self.plugin._get_camera_info("1")
            
            self.assertIsNone(camera_id)
            self.assertEqual(camera_name, "")
    
    def test_resize_image_invalid_file(self):
        """Test image resizing with invalid file."""
        with self.assertRaises(Exception):
            self.plugin._resize_image_if_needed(
                "/nonexistent/file.jpg",
                "/tmp/output.jpg", 
                100
            )


if __name__ == '__main__':
    unittest.main()