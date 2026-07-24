"""Tests for securityspy_image.cameras — address parsing and the registry."""

from securityspy_image import cameras


class TestParseCynicalAddress:
    def test_valid_address(self):
        assert cameras.parse_cynical_address("Front Door Camera (1)") == "1"

    def test_multi_digit(self):
        assert cameras.parse_cynical_address("Back Yard (12)") == "12"

    def test_whitespace_is_stripped(self):
        assert cameras.parse_cynical_address("Camera Name ( 5 )") == "5"

    def test_zero_padding_removed(self):
        assert cameras.parse_cynical_address("Camera (05)") == "5"

    def test_no_parentheses(self):
        assert cameras.parse_cynical_address("Invalid Address Format") is None

    def test_only_opening_paren(self):
        assert cameras.parse_cynical_address("Camera (incomplete") is None

    def test_only_closing_paren(self):
        assert cameras.parse_cynical_address("Camera incomplete)") is None

    def test_reversed_parens(self):
        assert cameras.parse_cynical_address("Camera )5(") is None

    def test_empty_parens(self):
        assert cameras.parse_cynical_address("Camera ()") is None

    def test_non_numeric(self):
        assert cameras.parse_cynical_address("Camera (abc)") is None


class TestParseFlyingdiverAddress:
    def test_zero_padded(self):
        assert cameras.parse_flyingdiver_address("server123:01") == "1"

    def test_multiple_zeros(self):
        assert cameras.parse_flyingdiver_address("server456:005") == "5"

    def test_no_padding(self):
        assert cameras.parse_flyingdiver_address("server789:12") == "12"

    def test_camera_zero(self):
        assert cameras.parse_flyingdiver_address("server123:00") == "0"
        assert cameras.parse_flyingdiver_address("server123:0") == "0"

    def test_no_colon(self):
        assert cameras.parse_flyingdiver_address("server123_01") is None

    def test_multiple_colons_is_invalid(self):
        assert cameras.parse_flyingdiver_address("server:123:01") is None

    def test_empty_server(self):
        assert cameras.parse_flyingdiver_address(":01") is None

    def test_empty_camera(self):
        assert cameras.parse_flyingdiver_address("server123:") is None


class TestSplitCameraId:
    def test_qualified_id(self):
        assert cameras.split_camera_id("cynical:5") == ("cynical", "5")

    def test_flyingdiver_id(self):
        assert cameras.split_camera_id("flyingdiver:03") == ("flyingdiver", "03")

    def test_legacy_bare_number(self):
        assert cameras.split_camera_id("5") == (None, "5")


class TestPluginRegistry:
    def test_backends_present(self):
        assert set(cameras.SECURITYSPY_PLUGINS) == {"cynical", "flyingdiver"}

    def test_cynical_config(self):
        config = cameras.SECURITYSPY_PLUGINS["cynical"]
        assert config["filter"] == "org.cynic.indigo.securityspy.camera"
        assert config["name"] == "Cynical SecuritySpy"
        assert config["address_parser"] is cameras.parse_cynical_address
        assert config["device_type_filter"] is None

    def test_flyingdiver_config(self):
        config = cameras.SECURITYSPY_PLUGINS["flyingdiver"]
        assert config["filter"] == "com.flyingdiver.indigoplugin.securityspy"
        assert config["name"] == "Spy Connect"
        assert config["address_parser"] is cameras.parse_flyingdiver_address
        assert config["device_type_filter"] == "spyCamera"
