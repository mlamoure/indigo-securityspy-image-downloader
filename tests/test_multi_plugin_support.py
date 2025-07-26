"""
Test suite for multi-plugin SecuritySpy support.

Tests the plugin's ability to work with both:
- Cynical SecuritySpy Plugin (org.cynic.indigo.securityspy.camera)
- FlyingDiver SecuritySpy Plugin (com.flyingdiver.indigoplugin.securityspy)
"""

import unittest
from unittest.mock import Mock, patch
import sys
import os

# Mock indigo before importing plugin
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

mock_indigo = MockIndigo()
sys.modules['indigo'] = mock_indigo

# Import plugin after mocking
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'SecuritySpy Image Downloader.indigoPlugin', 'Contents', 'Server Plugin'))
from plugin import Plugin, SECURITYSPY_PLUGINS


class TestMultiPluginSupport(unittest.TestCase):
    """Test cases for multi-plugin SecuritySpy support."""
    
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
    
    def test_securityspy_plugins_configuration(self):
        """Test that plugin configurations are properly defined."""
        self.assertIn('cynical', SECURITYSPY_PLUGINS)
        self.assertIn('flyingdiver', SECURITYSPY_PLUGINS)
        
        # Test Cynical plugin config
        cynical_config = SECURITYSPY_PLUGINS['cynical']
        self.assertEqual(cynical_config['filter'], 'org.cynic.indigo.securityspy.camera')
        self.assertEqual(cynical_config['address_parser'], '_parse_cynical_address')
        
        # Test FlyingDiver plugin config
        flyingdiver_config = SECURITYSPY_PLUGINS['flyingdiver']
        self.assertEqual(flyingdiver_config['filter'], 'com.flyingdiver.indigoplugin.securityspy')
        self.assertEqual(flyingdiver_config['address_parser'], '_parse_flyingdiver_address')
        self.assertEqual(flyingdiver_config['device_type_filter'], 'spyCamera')
        self.assertEqual(flyingdiver_config['name'], 'Spy Connect')
        
        # Test Cynical plugin config
        cynical_config = SECURITYSPY_PLUGINS['cynical']
        self.assertIsNone(cynical_config['device_type_filter'])  # No filtering for Cynical
        self.assertEqual(cynical_config['name'], 'Cynical SecuritySpy')
    
    def test_parse_cynical_address(self):
        """Test parsing of Cynical plugin camera addresses."""
        # Test valid address
        result = self.plugin._parse_cynical_address("Front Door Camera (1)")
        self.assertEqual(result, "1")
        
        # Test another valid address
        result = self.plugin._parse_cynical_address("Back Yard (12)")
        self.assertEqual(result, "12")
        
        # Test address with spaces in camera number
        result = self.plugin._parse_cynical_address("Camera Name ( 5 )")
        self.assertEqual(result, " 5 ")
        
        # Test invalid address - no parentheses
        result = self.plugin._parse_cynical_address("Invalid Address Format")
        self.assertIsNone(result)
        
        # Test invalid address - only opening parenthesis
        result = self.plugin._parse_cynical_address("Camera (incomplete")
        self.assertIsNone(result)
        
        # Test invalid address - only closing parenthesis
        result = self.plugin._parse_cynical_address("Camera incomplete)")
        self.assertIsNone(result)
        
        # Test empty parentheses
        result = self.plugin._parse_cynical_address("Camera ()")
        self.assertEqual(result, "")
    
    def test_parse_flyingdiver_address(self):
        """Test parsing of FlyingDiver plugin camera addresses."""
        # Test valid address with zero-padded camera number
        result = self.plugin._parse_flyingdiver_address("server123:01")
        self.assertEqual(result, "1")
        
        # Test valid address with multiple zeros
        result = self.plugin._parse_flyingdiver_address("server456:005")
        self.assertEqual(result, "5")
        
        # Test valid address with no zero-padding
        result = self.plugin._parse_flyingdiver_address("server789:12")
        self.assertEqual(result, "12")
        
        # Test valid address with camera number 0
        result = self.plugin._parse_flyingdiver_address("server123:00")
        self.assertEqual(result, "0")
        
        # Test valid address with only one zero
        result = self.plugin._parse_flyingdiver_address("server123:0")
        self.assertEqual(result, "0")
        
        # Test invalid address - no colon
        result = self.plugin._parse_flyingdiver_address("server123_01")
        self.assertIsNone(result)
        
        # Test address with multiple colons (should take first split)
        result = self.plugin._parse_flyingdiver_address("server:123:01")
        self.assertEqual(result, "123:01")
        
        # Test invalid address - empty server part
        result = self.plugin._parse_flyingdiver_address(":01")
        self.assertIsNone(result)
        
        # Test invalid address - empty camera part
        result = self.plugin._parse_flyingdiver_address("server123:")
        self.assertIsNone(result)
    
    @patch('plugin.indigo.devices.iter')
    def test_discover_cameras_cynical_only(self, mock_iter):
        """Test camera discovery with only Cynical plugin cameras."""
        def mock_device_iter(filter=None):
            if filter == 'org.cynic.indigo.securityspy.camera':
                mock_camera1 = Mock()
                mock_camera1.enabled = True
                mock_camera1.name = "Front Door"
                mock_camera1.address = "Front Door Camera (1)"
                
                mock_camera2 = Mock()
                mock_camera2.enabled = True
                mock_camera2.name = "Back Yard"
                mock_camera2.address = "Back Yard Camera (2)"
                
                return [mock_camera1, mock_camera2]
            return []
        
        mock_iter.side_effect = mock_device_iter
        
        cameras = self.plugin._discover_cameras()
        
        self.assertEqual(len(cameras), 2)
        self.assertIn(("1", "Front Door", "cynical"), cameras)
        self.assertIn(("2", "Back Yard", "cynical"), cameras)
    
    @patch('plugin.indigo.devices.iter')
    def test_discover_cameras_flyingdiver_only(self, mock_iter):
        """Test camera discovery with only FlyingDiver plugin cameras."""
        def mock_device_iter(filter=None):
            if filter == 'com.flyingdiver.indigoplugin.securityspy':
                mock_camera1 = Mock()
                mock_camera1.enabled = True
                mock_camera1.name = "Garage Camera"
                mock_camera1.address = "server123:01"
                mock_camera1.deviceTypeId = "spyCamera"  # Camera device
                
                mock_camera2 = Mock()
                mock_camera2.enabled = True
                mock_camera2.name = "Driveway Camera"
                mock_camera2.address = "server123:05"
                mock_camera2.deviceTypeId = "spyCamera"  # Camera device
                
                return [mock_camera1, mock_camera2]
            return []
        
        mock_iter.side_effect = mock_device_iter
        
        cameras = self.plugin._discover_cameras()
        
        self.assertEqual(len(cameras), 2)
        self.assertIn(("1", "Garage Camera", "flyingdiver"), cameras)
        self.assertIn(("5", "Driveway Camera", "flyingdiver"), cameras)
    
    @patch('plugin.indigo.devices.iter')
    def test_discover_cameras_both_plugins(self, mock_iter):
        """Test camera discovery with both plugins present."""
        def mock_device_iter(filter=None):
            if filter == 'org.cynic.indigo.securityspy.camera':
                mock_camera1 = Mock()
                mock_camera1.enabled = True
                mock_camera1.name = "Cynical Camera 1"
                mock_camera1.address = "Cynical Camera 1 (1)"
                return [mock_camera1]
            elif filter == 'com.flyingdiver.indigoplugin.securityspy':
                mock_camera2 = Mock()
                mock_camera2.enabled = True
                mock_camera2.name = "FlyingDiver Camera 2"
                mock_camera2.address = "server123:02"
                mock_camera2.deviceTypeId = "spyCamera"  # Camera device
                return [mock_camera2]
            return []
        
        mock_iter.side_effect = mock_device_iter
        
        cameras = self.plugin._discover_cameras()
        
        self.assertEqual(len(cameras), 2)
        self.assertIn(("1", "Cynical Camera 1", "cynical"), cameras)
        self.assertIn(("2", "FlyingDiver Camera 2", "flyingdiver"), cameras)
    
    @patch('plugin.indigo.devices.iter')
    def test_discover_cameras_disabled_devices(self, mock_iter):
        """Test camera discovery ignores disabled devices."""
        def mock_device_iter(filter=None):
            if filter == 'org.cynic.indigo.securityspy.camera':
                mock_camera1 = Mock()
                mock_camera1.enabled = True
                mock_camera1.name = "Enabled Camera"
                mock_camera1.address = "Enabled Camera (1)"
                
                mock_camera2 = Mock()
                mock_camera2.enabled = False  # Disabled
                mock_camera2.name = "Disabled Camera"
                mock_camera2.address = "Disabled Camera (2)"
                
                return [mock_camera1, mock_camera2]
            return []
        
        mock_iter.side_effect = mock_device_iter
        
        cameras = self.plugin._discover_cameras()
        
        self.assertEqual(len(cameras), 1)
        self.assertIn(("1", "Enabled Camera", "cynical"), cameras)
        # Disabled camera should not be included
        self.assertNotIn(("2", "Disabled Camera", "cynical"), cameras)
    
    @patch('plugin.indigo.devices.iter')
    def test_discover_cameras_invalid_addresses(self, mock_iter):
        """Test camera discovery handles invalid addresses gracefully."""
        def mock_device_iter(filter=None):
            if filter == 'org.cynic.indigo.securityspy.camera':
                mock_camera1 = Mock()
                mock_camera1.enabled = True
                mock_camera1.name = "Valid Camera"
                mock_camera1.address = "Valid Camera (1)"
                
                mock_camera2 = Mock()
                mock_camera2.enabled = True
                mock_camera2.name = "Invalid Camera"
                mock_camera2.address = "Invalid Address Format"  # No parentheses
                
                return [mock_camera1, mock_camera2]
            return []
        
        mock_iter.side_effect = mock_device_iter
        
        cameras = self.plugin._discover_cameras()
        
        # Only valid camera should be included
        self.assertEqual(len(cameras), 1)
        self.assertIn(("1", "Valid Camera", "cynical"), cameras)
    
    @patch('plugin.indigo.devices.iter')
    def test_get_camera_info_multi_plugin(self, mock_iter):
        """Test _get_camera_info works across multiple plugins."""
        def mock_device_iter(filter=None):
            if filter == 'org.cynic.indigo.securityspy.camera':
                mock_camera1 = Mock()
                mock_camera1.enabled = True
                mock_camera1.name = "Cynical Camera"
                mock_camera1.address = "Cynical Camera (5)"
                mock_camera1.id = 12345
                return [mock_camera1]
            elif filter == 'com.flyingdiver.indigoplugin.securityspy':
                mock_camera2 = Mock()
                mock_camera2.enabled = True
                mock_camera2.name = "FlyingDiver Camera"
                mock_camera2.address = "server123:03"
                mock_camera2.deviceTypeId = "spyCamera"
                mock_camera2.id = 67890
                return [mock_camera2]
            return []
        
        mock_iter.side_effect = mock_device_iter
        
        # Test finding Cynical camera with qualified ID
        camera_id, camera_name = self.plugin._get_camera_info("cynical:5")
        self.assertEqual(camera_id, 12345)
        self.assertEqual(camera_name, "Cynical Camera")
        
        # Test finding Cynical camera with legacy numeric ID
        camera_id, camera_name = self.plugin._get_camera_info("5")
        self.assertEqual(camera_id, 12345)
        self.assertEqual(camera_name, "Cynical Camera")
        
        # Test finding FlyingDiver camera with explicit plugin prefix
        camera_id, camera_name = self.plugin._get_camera_info("flyingdiver:3")
        self.assertEqual(camera_id, 67890)
        self.assertEqual(camera_name, "FlyingDiver Camera")
        
        # Test camera not found
        camera_id, camera_name = self.plugin._get_camera_info("cynical:99")
        self.assertIsNone(camera_id)
        self.assertEqual(camera_name, "")
    
    @patch('plugin.indigo.devices.iter')
    def test_camera_list_generator_multi_plugin(self, mock_iter):
        """Test camera list generator with multiple plugins."""
        def mock_device_iter(filter=None):
            if filter == 'org.cynic.indigo.securityspy.camera':
                mock_camera1 = Mock()
                mock_camera1.enabled = True
                mock_camera1.name = "Cynical Camera"
                mock_camera1.address = "Cynical Camera (1)"
                return [mock_camera1]
            elif filter == 'com.flyingdiver.indigoplugin.securityspy':
                mock_camera2 = Mock()
                mock_camera2.enabled = True
                mock_camera2.name = "FlyingDiver Camera"
                mock_camera2.address = "server123:02"
                mock_camera2.deviceTypeId = "spyCamera"
                return [mock_camera2]
            return []
        
        mock_iter.side_effect = mock_device_iter
        
        camera_list = self.plugin.camera_list_generator()
        
        # Should have 2 cameras plus "none" option
        self.assertEqual(len(camera_list), 3)
        
        # Check camera entries (with plugin names in display names)
        camera_entries = [entry for entry in camera_list if entry[0] != "-1"]
        self.assertEqual(len(camera_entries), 2)
        
        # Verify cameras are sorted by number (with new unique ID format)
        self.assertEqual(camera_entries[0][0], "cynical:1")  # Camera 1 first
        self.assertEqual(camera_entries[1][0], "flyingdiver:2")  # Camera 2 second
        
        # Verify plugin names are included in display names
        self.assertIn("Cynical SecuritySpy", camera_entries[0][1])
        self.assertIn("Spy Connect", camera_entries[1][1])
        
        # Verify "none" option is present
        self.assertIn(("-1", "none"), camera_list)
    
    @patch('plugin.indigo.devices.iter')
    def test_discover_cameras_flyingdiver_device_type_filtering(self, mock_iter):
        """Test that FlyingDiver plugin filters out spyServer devices and only includes spyCamera devices."""
        def mock_device_iter(filter=None):
            if filter == 'com.flyingdiver.indigoplugin.securityspy':
                # Mock a camera device (should be included)
                mock_camera = Mock()
                mock_camera.enabled = True
                mock_camera.name = "Front Door Camera"
                mock_camera.address = "server123:01"
                mock_camera.deviceTypeId = "spyCamera"
                
                # Mock a server device (should be excluded)
                mock_server = Mock()
                mock_server.enabled = True
                mock_server.name = "SecuritySpy Server"
                mock_server.address = "10.66.0.95:8006"
                mock_server.deviceTypeId = "spyServer"
                
                return [mock_camera, mock_server]
            return []
        
        mock_iter.side_effect = mock_device_iter
        
        cameras = self.plugin._discover_cameras()
        
        # Should only find the camera, not the server
        self.assertEqual(len(cameras), 1)
        self.assertIn(("1", "Front Door Camera", "flyingdiver"), cameras)
        
        # Verify server device is not included
        server_found = any("SecuritySpy Server" in camera[1] for camera in cameras)
        self.assertFalse(server_found, "spyServer device should be filtered out")


if __name__ == '__main__':
    unittest.main()