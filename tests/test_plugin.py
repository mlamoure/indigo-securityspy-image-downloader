"""Tests for the plugin.py Indigo adapter."""

import logging
import os

import indigo
import pytest
from PIL import Image

from plugin import Plugin
from securityspy_image.exceptions import DestinationError


@pytest.fixture
def fake_download(monkeypatch):
    """Replace http_client.download_image with one that writes a real JPEG."""
    from securityspy_image import http_client

    calls = []
    # vary the color per call so PIL's GIF writer can't merge identical frames
    colors = ("red", "green", "blue")

    def _fake(url, save_path, auth=None, verify_ssl=False, timeout=30, session=None):
        color = colors[len(calls) % len(colors)]
        calls.append({"url": url, "save_path": save_path, "verify_ssl": verify_ssl})
        Image.new("RGB", (80, 40), color=color).save(save_path, "JPEG")
        return os.path.getsize(save_path)

    monkeypatch.setattr(http_client, "download_image", _fake)
    return calls


def _make_plugin(prefs):
    return Plugin("com.test.plugin", "Test Plugin", "1.0.0", prefs)


class TestInitialization:
    def test_loads_connection_settings(self, plugin):
        assert plugin.security_spy_ip == "192.168.1.100"
        assert plugin.security_spy_port == "8000"
        assert plugin.security_spy_login == "testuser"
        assert plugin.security_spy_pass == "testpass"
        assert plugin.use_ssl is False
        assert plugin.security_spy_auth_type == "basic"
        assert plugin.configured is True
        assert plugin.security_spy_url == "http://192.168.1.100:8000"

    def test_ssl_url(self, plugin_prefs):
        plugin_prefs["ssl"] = True
        plugin = _make_plugin(plugin_prefs)
        assert plugin.security_spy_url == "https://192.168.1.100:8000"

    def test_no_credentials_means_no_auth(self, plugin_prefs):
        plugin_prefs.update({"login": "", "password": ""})
        plugin = _make_plugin(plugin_prefs)
        assert plugin.security_spy_auth_type is None

    def test_missing_config_is_unconfigured(self):
        plugin = _make_plugin({"debug": False})
        assert plugin.configured is False
        assert plugin.security_spy_url == ""

    def test_verify_ssl_defaults_off(self, plugin):
        assert plugin.verify_ssl is False

    def test_verify_ssl_pref(self, plugin_prefs):
        plugin_prefs["verify_ssl"] = True
        assert _make_plugin(plugin_prefs).verify_ssl is True


class TestDebugLogging:
    """The debug pref must take effect at startup, not only after the config
    dialog is opened (this was a long-standing bug)."""

    def test_debug_pref_enables_debug_level_at_startup(self, plugin_prefs):
        plugin = _make_plugin(plugin_prefs)  # debug: True
        assert plugin.indigo_log_handler.level == logging.DEBUG

    def test_no_debug_pref_means_info_level(self, plugin_prefs):
        plugin_prefs["debug"] = False
        plugin = _make_plugin(plugin_prefs)
        assert plugin.indigo_log_handler.level == logging.INFO


class TestPrefsValidation:
    def test_both_empty_is_valid_for_custom_url_only_use(self, plugin):
        result = plugin.validatePrefsConfigUi({"ip": "", "port": ""})
        assert result[0] is True

    def test_port_without_ip_blocks_save(self, plugin):
        ok, _, errors = plugin.validatePrefsConfigUi({"ip": "", "port": "8000"})
        assert ok is False
        assert "ip" in errors

    def test_ip_without_port_blocks_save(self, plugin):
        ok, _, errors = plugin.validatePrefsConfigUi({"ip": "host", "port": ""})
        assert ok is False
        assert "port" in errors

    def test_non_integer_port_blocks_save(self, plugin):
        ok, _, errors = plugin.validatePrefsConfigUi({"ip": "host", "port": "abc"})
        assert ok is False
        assert "port" in errors

    def test_out_of_range_port_blocks_save(self, plugin):
        ok, _, errors = plugin.validatePrefsConfigUi({"ip": "host", "port": "70000"})
        assert ok is False
        assert "port" in errors

    def test_unreachable_server_warns_but_saves(self, plugin, monkeypatch):
        monkeypatch.setattr(
            "socket.create_connection",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("refused")),
        )
        result = plugin.validatePrefsConfigUi({"ip": "192.0.2.1", "port": "8000"})
        assert result[0] is True

    def test_reachable_server_saves(self, plugin, monkeypatch):
        class _Conn:
            def close(self):
                pass

        monkeypatch.setattr("socket.create_connection", lambda *a, **k: _Conn())
        result = plugin.validatePrefsConfigUi({"ip": "192.168.1.100", "port": "8000"})
        assert result[0] is True


class TestClosedPrefs:
    def test_applies_new_values(self, plugin):
        plugin.closedPrefsConfigUi(
            {
                "debug": False,
                "ip": "192.168.1.101",
                "port": "8001",
                "login": "newuser",
                "password": "newpass",
                "ssl": True,
            },
            False,
        )
        assert plugin.security_spy_ip == "192.168.1.101"
        assert plugin.security_spy_url == "https://192.168.1.101:8001"
        assert plugin.security_spy_auth_type == "basic"
        assert plugin.indigo_log_handler.level == logging.INFO

    def test_cancelled_dialog_changes_nothing(self, plugin):
        plugin.closedPrefsConfigUi({"ip": "192.168.1.999"}, True)
        assert plugin.security_spy_ip == "192.168.1.100"

    def test_empty_login_clears_auth(self, plugin):
        plugin.closedPrefsConfigUi(
            {"ip": "192.168.1.100", "port": "8000", "login": "", "password": ""},
            False,
        )
        assert plugin.security_spy_auth_type is None


class TestPrepareTextValue:
    def test_returns_str(self, plugin):
        assert plugin.prepare_text_value("test string") == "test string"

    def test_strips_whitespace(self, plugin):
        assert plugin.prepare_text_value("  test string  ") == "test string"

    def test_none_passthrough(self, plugin):
        assert plugin.prepare_text_value(None) is None

    def test_empty_string(self, plugin):
        assert plugin.prepare_text_value("") == ""


class TestDestinationPath:
    def test_direct_path(self, plugin, tmp_path):
        dest = str(tmp_path / "test.jpg")
        action = indigo.PluginAction({"useVariable": False, "destination": dest})
        assert plugin._get_destination_path(action) == dest

    def test_variable_path(self, plugin, tmp_path):
        dest = str(tmp_path / "var_test.jpg")
        indigo.variables[123] = indigo.Variable(dest)
        action = indigo.PluginAction(
            {"useVariable": True, "destinationVariable": "123"}
        )
        assert plugin._get_destination_path(action) == dest

    def test_missing_variable_falls_back_to_direct(self, plugin, tmp_path):
        dest = str(tmp_path / "fallback.jpg")
        action = indigo.PluginAction(
            {"useVariable": True, "destinationVariable": "999", "destination": dest}
        )
        assert plugin._get_destination_path(action) == dest

    def test_missing_directory_raises(self, plugin):
        action = indigo.PluginAction(
            {"useVariable": False, "destination": "/nonexistent/dir/test.jpg"}
        )
        with pytest.raises(DestinationError, match="does not exist"):
            plugin._get_destination_path(action)

    def test_empty_path_raises(self, plugin):
        action = indigo.PluginAction({"useVariable": False, "destination": ""})
        with pytest.raises(DestinationError, match="not provided"):
            plugin._get_destination_path(action)


class TestBuildImageUrl:
    def test_securityspy_camera(self, plugin):
        indigo.devices.by_filter["org.cynic.indigo.securityspy.camera"] = [
            indigo.Device(name="Test Camera", address="Test Camera (5)")
        ]
        action = indigo.PluginAction({"type": "securityspy", "cam1": "cynical:5"})
        url, camera_name, server_resized = plugin._build_image_url(action)
        assert url == "http://192.168.1.100:8000/++image?cameraNum=5"
        assert camera_name == "Test Camera"
        assert server_resized is False

    def test_securityspy_camera_with_width(self, plugin):
        indigo.devices.by_filter["org.cynic.indigo.securityspy.camera"] = [
            indigo.Device(name="Test Camera", address="Test Camera (5)")
        ]
        action = indigo.PluginAction({"type": "securityspy", "cam1": "cynical:5"})
        url, _, server_resized = plugin._build_image_url(action, image_size=640)
        assert url == "http://192.168.1.100:8000/++image?cameraNum=5&width=640"
        assert server_resized is True

    def test_legacy_camera_id(self, plugin):
        indigo.devices.by_filter["org.cynic.indigo.securityspy.camera"] = [
            indigo.Device(name="Test Camera", address="Test Camera (5)")
        ]
        action = indigo.PluginAction({"type": "securityspy", "cam1": "5"})
        url, camera_name, _ = plugin._build_image_url(action)
        assert url == "http://192.168.1.100:8000/++image?cameraNum=5"
        assert camera_name == "Test Camera"

    def test_custom_url(self, plugin):
        action = indigo.PluginAction(
            {"type": "urlType", "url": "http://example.com/camera.jpg"}
        )
        url, camera_name, server_resized = plugin._build_image_url(
            action, image_size=640
        )
        assert url == "http://example.com/camera.jpg"
        assert camera_name == ""
        assert server_resized is False  # custom URLs always resize locally


class TestImageSize:
    def test_valid(self, plugin):
        assert plugin._get_image_size(indigo.PluginAction({"imageSize": "800"})) == 800

    def test_invalid(self, plugin):
        assert plugin._get_image_size(indigo.PluginAction({"imageSize": "nan"})) == -1

    def test_empty(self, plugin):
        assert plugin._get_image_size(indigo.PluginAction({"imageSize": ""})) == -1


class TestAuthConfig:
    def test_securityspy_uses_plugin_credentials(self, plugin):
        action = indigo.PluginAction({"type": "securityspy"})
        assert plugin._get_auth_config(action) == ("basic", "testuser", "testpass")

    def test_url_with_auth(self, plugin):
        action = indigo.PluginAction(
            {"type": "urlType", "useAuth": "digest", "login": "u", "password": "p"}
        )
        assert plugin._get_auth_config(action) == ("digest", "u", "p")

    def test_url_without_auth(self, plugin):
        action = indigo.PluginAction({"type": "urlType", "useAuth": "none"})
        assert plugin._get_auth_config(action) == (None, None, None)


class TestDownloadImageAction:
    def test_securityspy_source_requires_config(self, plugin):
        plugin.configured = False
        action = indigo.PluginAction(
            {"type": "securityspy", "destination": "/tmp/test.jpg"}
        )
        assert plugin.download_image_action(action, None) is False

    def test_custom_url_works_without_securityspy_config(self, fake_download, tmp_path):
        plugin = _make_plugin({"debug": False})  # no SecuritySpy settings at all
        assert plugin.configured is False
        dest = str(tmp_path / "out.jpg")
        action = indigo.PluginAction(
            {
                "type": "urlType",
                "url": "http://example.com/cam.jpg",
                "destination": dest,
            }
        )
        assert plugin.download_image_action(action, None) is True
        assert os.path.exists(dest)

    def test_securityspy_resize_is_server_side(self, plugin, fake_download, tmp_path):
        indigo.devices.by_filter["org.cynic.indigo.securityspy.camera"] = [
            indigo.Device(name="Test Camera", address="Test Camera (5)")
        ]
        dest = str(tmp_path / "out.jpg")
        action = indigo.PluginAction(
            {
                "type": "securityspy",
                "cam1": "cynical:5",
                "destination": dest,
                "imageSize": "50",
            }
        )
        assert plugin.download_image_action(action, None) is True
        assert "width=50" in fake_download[0]["url"]
        # no local PIL pass: the (fake) 80x40 server response lands untouched
        with Image.open(dest) as img:
            assert img.size == (80, 40)

    def test_custom_url_download(self, plugin, fake_download, tmp_path):
        dest = str(tmp_path / "out.jpg")
        action = indigo.PluginAction(
            {
                "type": "urlType",
                "url": "http://example.com/cam.jpg",
                "destination": dest,
            }
        )
        assert plugin.download_image_action(action, None) is True
        assert os.path.exists(dest)
        assert fake_download[0]["url"] == "http://example.com/cam.jpg"

    def test_download_with_resize(self, plugin, fake_download, tmp_path):
        dest = str(tmp_path / "out.jpg")
        action = indigo.PluginAction(
            {
                "type": "urlType",
                "url": "http://example.com/cam.jpg",
                "destination": dest,
                "imageSize": "50",
            }
        )
        assert plugin.download_image_action(action, None) is True
        with Image.open(dest) as img:
            assert img.width <= 50
        # the resize temp file must be cleaned up
        assert os.listdir(tmp_path) == ["out.jpg"]

    def test_download_failure_returns_false(self, plugin, monkeypatch, tmp_path):
        from securityspy_image import http_client
        from securityspy_image.exceptions import DownloadError

        def _fail(*args, **kwargs):
            raise DownloadError("boom")

        monkeypatch.setattr(http_client, "download_image", _fail)
        dest = str(tmp_path / "out.jpg")
        action = indigo.PluginAction(
            {
                "type": "urlType",
                "url": "http://example.com/cam.jpg",
                "destination": dest,
            }
        )
        assert plugin.download_image_action(action, None) is False

    def test_missing_destination_returns_false(self, plugin):
        action = indigo.PluginAction(
            {"type": "urlType", "url": "http://x", "destination": ""}
        )
        assert plugin.download_image_action(action, None) is False


class TestStitchImageAction:
    def _register_cameras(self):
        indigo.devices.by_filter["org.cynic.indigo.securityspy.camera"] = [
            indigo.Device(name="Cam One", address="Cam One (1)"),
            indigo.Device(name="Cam Two", address="Cam Two (2)"),
        ]

    def test_not_configured_fails(self, plugin):
        plugin.configured = False
        action = indigo.PluginAction({"destination": "/tmp/test.jpg"})
        assert plugin.stitch_image_action(action, None) is False

    def test_horizontal_layout(self, plugin, fake_download, tmp_path):
        self._register_cameras()
        dest = str(tmp_path / "stitched.jpg")
        action = indigo.PluginAction(
            {
                "destination": dest,
                "cam1": "cynical:1",
                "cam2": "cynical:2",
                "layout": "horizontal",
            }
        )
        assert plugin.stitch_image_action(action, None) is True
        with Image.open(dest) as img:
            assert img.size == (160, 40)  # two 80x40 frames side by side

    def test_grid_layout(self, plugin, fake_download, tmp_path):
        self._register_cameras()
        dest = str(tmp_path / "stitched.jpg")
        action = indigo.PluginAction(
            {
                "destination": dest,
                "cam1": "cynical:1",
                "cam2": "cynical:2",
                "layout": "grid",
            }
        )
        assert plugin.stitch_image_action(action, None) is True
        with Image.open(dest) as img:
            assert img.size == (160, 40)  # 1 row of 2 cells

    def test_unknown_layout_falls_back_to_vertical(
        self, plugin, fake_download, tmp_path
    ):
        self._register_cameras()
        dest = str(tmp_path / "stitched.jpg")
        action = indigo.PluginAction(
            {
                "destination": dest,
                "cam1": "cynical:1",
                "cam2": "cynical:2",
                "layout": "diagonal",
            }
        )
        assert plugin.stitch_image_action(action, None) is True
        with Image.open(dest) as img:
            assert img.size == (80, 80)  # vertical fallback

    def test_stitch_resize_is_server_side(self, plugin, fake_download, tmp_path):
        self._register_cameras()
        dest = str(tmp_path / "stitched.jpg")
        action = indigo.PluginAction(
            {
                "destination": dest,
                "cam1": "cynical:1",
                "cam2": "cynical:2",
                "imageSize": "50",
            }
        )
        assert plugin.stitch_image_action(action, None) is True
        assert all("width=50" in call["url"] for call in fake_download)
        # frames arrive "pre-scaled" from the (fake) server; no PIL clamp
        with Image.open(dest) as img:
            assert img.size == (80, 80)

    def test_stitches_two_cameras(self, plugin, fake_download, tmp_path):
        self._register_cameras()
        dest = str(tmp_path / "stitched.jpg")
        action = indigo.PluginAction(
            {"destination": dest, "cam1": "cynical:1", "cam2": "cynical:2"}
        )
        assert plugin.stitch_image_action(action, None) is True
        with Image.open(dest) as img:
            assert img.size == (80, 80)  # two 80x40 frames stacked
        # temp download files must be cleaned up
        assert os.listdir(tmp_path) == ["stitched.jpg"]
        assert [c["url"] for c in fake_download] == [
            "http://192.168.1.100:8000/++image?cameraNum=1",
            "http://192.168.1.100:8000/++image?cameraNum=2",
        ]

    def test_skips_failed_camera(self, plugin, monkeypatch, tmp_path):
        from securityspy_image import http_client
        from securityspy_image.exceptions import DownloadError

        self._register_cameras()
        calls = []

        def _flaky(url, save_path, **kwargs):
            calls.append(url)
            if "cameraNum=1" in url:
                raise DownloadError("camera offline")
            Image.new("RGB", (80, 40), color="blue").save(save_path, "JPEG")
            return os.path.getsize(save_path)

        monkeypatch.setattr(http_client, "download_image", _flaky)
        dest = str(tmp_path / "stitched.jpg")
        action = indigo.PluginAction(
            {"destination": dest, "cam1": "cynical:1", "cam2": "cynical:2"}
        )
        assert plugin.stitch_image_action(action, None) is True
        with Image.open(dest) as img:
            assert img.size == (80, 40)  # only the one successful frame

    def test_no_images_fails(self, plugin, monkeypatch, tmp_path):
        from securityspy_image import http_client
        from securityspy_image.exceptions import DownloadError

        self._register_cameras()
        monkeypatch.setattr(
            http_client,
            "download_image",
            lambda *a, **k: (_ for _ in ()).throw(DownloadError("offline")),
        )
        action = indigo.PluginAction(
            {"destination": str(tmp_path / "s.jpg"), "cam1": "cynical:1"}
        )
        assert plugin.stitch_image_action(action, None) is False


class TestAnimatedGifAction:
    def test_creates_gif_with_expected_frames(
        self, plugin, fake_download, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("time.sleep", lambda seconds: None)
        dest = str(tmp_path / "clip.jpg")
        action = indigo.PluginAction(
            {
                "type": "urlType",
                "url": "http://example.com/cam.jpg",
                "destination": dest,
                "gif": True,
                "gifTime": "2",
            }
        )
        assert plugin.download_image_action(action, None) is True
        gif_path = str(tmp_path / "clip.gif")  # extension is swapped to .gif
        assert os.path.exists(gif_path)
        with Image.open(gif_path) as gif:
            assert gif.n_frames == 2  # frames at t=0 and t=2
        assert os.listdir(tmp_path) == ["clip.gif"]

    def test_all_frames_failing_returns_false(self, plugin, monkeypatch, tmp_path):
        from securityspy_image import http_client
        from securityspy_image.exceptions import DownloadError

        monkeypatch.setattr("time.sleep", lambda seconds: None)
        monkeypatch.setattr(
            http_client,
            "download_image",
            lambda *a, **k: (_ for _ in ()).throw(DownloadError("offline")),
        )
        action = indigo.PluginAction(
            {
                "type": "urlType",
                "url": "http://example.com/cam.jpg",
                "destination": str(tmp_path / "clip.gif"),
                "gif": True,
                "gifTime": "2",
            }
        )
        assert plugin.download_image_action(action, None) is False
