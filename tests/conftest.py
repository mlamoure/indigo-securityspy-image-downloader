"""
Pytest configuration and fixtures for SecuritySpy Image Downloader tests.
"""

import pytest
import tempfile
import shutil
from unittest.mock import Mock


@pytest.fixture
def temp_dir():
    """Create and cleanup a temporary directory for tests."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_indigo_plugin_prefs():
    """Standard plugin preferences for testing."""
    return {
        "ip": "192.168.1.100",
        "port": "8000", 
        "login": "testuser",
        "password": "testpass",
        "ssl": False,
        "debug": True
    }


@pytest.fixture
def mock_indigo_action():
    """Create a mock Indigo action object."""
    def _create_action(props):
        action = Mock()
        action.props = props
        return action
    return _create_action


@pytest.fixture
def mock_indigo_device():
    """Create a mock Indigo device object."""
    device = Mock()
    device.name = "Test Device"
    device.id = 12345
    device.enabled = True
    return device