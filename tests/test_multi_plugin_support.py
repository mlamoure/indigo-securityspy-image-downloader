"""Tests for multi-plugin camera discovery (Cynical + FlyingDiver backends)."""

import indigo

CYNICAL_FILTER = "org.cynic.indigo.securityspy.camera"
FLYINGDIVER_FILTER = "com.flyingdiver.indigoplugin.securityspy"


def _cynical_camera(name, address, enabled=True):
    return indigo.Device(name=name, address=address, enabled=enabled)


def _flyingdiver_device(name, address, device_type="spyCamera", enabled=True):
    return indigo.Device(
        name=name, address=address, deviceTypeId=device_type, enabled=enabled
    )


class TestDiscoverCameras:
    def test_cynical_only(self, plugin):
        indigo.devices.by_filter[CYNICAL_FILTER] = [
            _cynical_camera("Front Door", "Front Door Camera (1)"),
            _cynical_camera("Back Yard", "Back Yard Camera (2)"),
        ]
        cameras = plugin._discover_cameras()
        assert ("1", "Front Door", "cynical") in cameras
        assert ("2", "Back Yard", "cynical") in cameras
        assert len(cameras) == 2

    def test_flyingdiver_only(self, plugin):
        indigo.devices.by_filter[FLYINGDIVER_FILTER] = [
            _flyingdiver_device("Garage Camera", "server123:01"),
            _flyingdiver_device("Driveway Camera", "server123:05"),
        ]
        cameras = plugin._discover_cameras()
        assert ("1", "Garage Camera", "flyingdiver") in cameras
        assert ("5", "Driveway Camera", "flyingdiver") in cameras
        assert len(cameras) == 2

    def test_both_plugins(self, plugin):
        indigo.devices.by_filter[CYNICAL_FILTER] = [
            _cynical_camera("Cynical Camera 1", "Cynical Camera 1 (1)")
        ]
        indigo.devices.by_filter[FLYINGDIVER_FILTER] = [
            _flyingdiver_device("FlyingDiver Camera 2", "server123:02")
        ]
        cameras = plugin._discover_cameras()
        assert ("1", "Cynical Camera 1", "cynical") in cameras
        assert ("2", "FlyingDiver Camera 2", "flyingdiver") in cameras
        assert len(cameras) == 2

    def test_disabled_devices_skipped(self, plugin):
        indigo.devices.by_filter[CYNICAL_FILTER] = [
            _cynical_camera("Enabled Camera", "Enabled Camera (1)"),
            _cynical_camera("Disabled Camera", "Disabled Camera (2)", enabled=False),
        ]
        cameras = plugin._discover_cameras()
        assert cameras == [("1", "Enabled Camera", "cynical")]

    def test_invalid_addresses_skipped(self, plugin):
        indigo.devices.by_filter[CYNICAL_FILTER] = [
            _cynical_camera("Valid Camera", "Valid Camera (1)"),
            _cynical_camera("Invalid Camera", "Invalid Address Format"),
        ]
        cameras = plugin._discover_cameras()
        assert cameras == [("1", "Valid Camera", "cynical")]

    def test_flyingdiver_server_devices_filtered_out(self, plugin):
        indigo.devices.by_filter[FLYINGDIVER_FILTER] = [
            _flyingdiver_device("Front Door Camera", "server123:01"),
            _flyingdiver_device(
                "SecuritySpy Server", "10.66.0.95:8006", device_type="spyServer"
            ),
        ]
        cameras = plugin._discover_cameras()
        assert cameras == [("1", "Front Door Camera", "flyingdiver")]


class TestGetCameraInfo:
    def _register(self):
        self.cynical = _cynical_camera("Cynical Camera", "Cynical Camera (5)")
        self.flyingdiver = _flyingdiver_device("FlyingDiver Camera", "server123:03")
        indigo.devices.by_filter[CYNICAL_FILTER] = [self.cynical]
        indigo.devices.by_filter[FLYINGDIVER_FILTER] = [self.flyingdiver]

    def test_qualified_cynical_id(self, plugin):
        self._register()
        assert plugin._get_camera_info("cynical:5") == (
            self.cynical.id,
            "Cynical Camera",
        )

    def test_legacy_id_maps_to_cynical(self, plugin):
        self._register()
        assert plugin._get_camera_info("5") == (self.cynical.id, "Cynical Camera")

    def test_qualified_flyingdiver_id(self, plugin):
        self._register()
        assert plugin._get_camera_info("flyingdiver:3") == (
            self.flyingdiver.id,
            "FlyingDiver Camera",
        )

    def test_unknown_camera(self, plugin):
        self._register()
        assert plugin._get_camera_info("cynical:99") == (None, "")

    def test_unknown_plugin_prefix(self, plugin):
        self._register()
        assert plugin._get_camera_info("otherplugin:1") == (None, "")


class TestCameraListGenerator:
    def test_fallback_when_no_cameras(self, plugin):
        result = plugin.camera_list_generator()
        assert len(result) == 17  # 16 manual placeholders + "none"
        assert result[0] == ("0", "Camera 0 (Manual)")
        assert result[-1] == ("-1", "none")

    def test_multi_plugin_list_sorted_with_names(self, plugin):
        indigo.devices.by_filter[CYNICAL_FILTER] = [
            _cynical_camera("Cynical Camera", "Cynical Camera (1)")
        ]
        indigo.devices.by_filter[FLYINGDIVER_FILTER] = [
            _flyingdiver_device("FlyingDiver Camera", "server123:02")
        ]
        result = plugin.camera_list_generator()
        assert len(result) == 3  # two cameras + "none"
        camera_entries = [entry for entry in result if entry[0] != "-1"]
        assert camera_entries[0][0] == "cynical:1"
        assert camera_entries[1][0] == "flyingdiver:2"
        assert "Cynical SecuritySpy" in camera_entries[0][1]
        assert "Spy Connect" in camera_entries[1][1]
        assert ("-1", "none") in result
