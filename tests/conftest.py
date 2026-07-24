"""Pytest configuration: stub the `indigo` module before any plugin import.

The plugin runs inside Indigo's embedded Python where `indigo` is injected by
the host. Tests stub just the surface the plugin touches, following the same
approach as the other vtmikel plugins (Auto Lights, Roomie Remote).
"""

import io
import logging
import os
import sys
import types

import requests

indigo_stub = types.SimpleNamespace()


class Devices:
    """indigo.devices — supports iter(filter=...) via per-filter registries.

    Tests populate `indigo.devices.by_filter["<plugin id>"]` with Device
    instances to simulate installed SecuritySpy plugins.
    """

    def __init__(self):
        self.by_filter = {}

    def iter(self, filter=""):
        return iter(list(self.by_filter.get(filter, [])))

    def clear(self):
        self.by_filter.clear()


class Device:
    _next_id = 100

    def __init__(self, name="", address="", deviceTypeId="", enabled=True, dev_id=None):
        if dev_id is None:
            Device._next_id += 1
            dev_id = Device._next_id
        self.id = dev_id
        self.name = name
        self.address = address
        self.deviceTypeId = deviceTypeId
        self.enabled = enabled


class Variable:
    def __init__(self, value=""):
        self.value = value


class PluginAction:
    def __init__(self, props=None):
        self.props = props or {}


class IndigoDict(dict):
    pass


class _DummyHandler(logging.Handler):
    def __init__(self, baseFilename="/tmp/Logs/plugin.log"):
        super().__init__()
        self.baseFilename = baseFilename

    def emit(self, record):
        pass


class PluginBase:
    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs):
        self.pluginId = plugin_id
        self.pluginDisplayName = plugin_display_name
        self.pluginVersion = plugin_version
        self.pluginPrefs = plugin_prefs
        self.debug = False
        self.logger = logging.getLogger("Plugin")
        self.indigo_log_handler = _DummyHandler()
        self.plugin_file_handler = _DummyHandler()

    def substitute(self, text):
        return text

    def sleep(self, seconds):
        pass


indigo_stub.PluginBase = PluginBase
indigo_stub.PluginAction = PluginAction
indigo_stub.Device = Device
indigo_stub.Variable = Variable
indigo_stub.Dict = IndigoDict
indigo_stub.devices = Devices()
indigo_stub.variables = {}
indigo_stub.server = types.SimpleNamespace(log=lambda *args, **kwargs: None)

sys.modules["indigo"] = indigo_stub

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            "SecuritySpy Image Downloader.indigoPlugin",
            "Contents",
            "Server Plugin",
        )
    ),
)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fake_indigo():
    indigo_stub.devices.clear()
    indigo_stub.variables.clear()
    yield indigo_stub


@pytest.fixture
def plugin_prefs():
    return {
        "ip": "192.168.1.100",
        "port": "8000",
        "login": "testuser",
        "password": "testpass",
        "ssl": False,
        "debug": True,
    }


@pytest.fixture
def plugin(plugin_prefs):
    from plugin import Plugin

    return Plugin("com.test.plugin", "Test Plugin", "1.0.0", plugin_prefs)


# ---------------------------------------------------------------------------
# Fake HTTP layer — tests never touch the network
# ---------------------------------------------------------------------------


class _FakeRaw(io.BytesIO):
    """BytesIO subclass so download_image can set .decode_content on it."""


class FakeResponse:
    def __init__(self, content=b"fake-image-bytes", status_code=200):
        self.status_code = status_code
        self.raw = _FakeRaw(content)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"{self.status_code} error", response=self
            )


class FakeSession:
    """Injectable stand-in for `requests`; records calls, never hits the net."""

    def __init__(self, response=None, exc=None):
        self.response = response if response is not None else FakeResponse()
        self.exc = exc
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.exc is not None:
            raise self.exc
        return self.response


@pytest.fixture
def fake_session():
    return FakeSession()
