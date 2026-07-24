"""Camera address parsing and the supported SecuritySpy plugin registry."""

from typing import Optional, Tuple


def _normalize_camera_num(raw: str) -> Optional[str]:
    """Strip whitespace/zero-padding; None unless the value is a number."""
    value = raw.strip()
    if not value.isdigit():
        return None
    return str(int(value))


def parse_cynical_address(camera_address: str) -> Optional[str]:
    """Parse the Cynical plugin address format: "Camera Name (n)" -> "n"."""
    open_paren = camera_address.find("(")
    close_paren = camera_address.find(")")
    if open_paren == -1 or close_paren == -1 or close_paren < open_paren:
        return None
    return _normalize_camera_num(camera_address[open_paren + 1 : close_paren])


def parse_flyingdiver_address(camera_address: str) -> Optional[str]:
    """Parse the FlyingDiver plugin address format: "{server_id}:{n}" -> "n"."""
    if ":" not in camera_address:
        return None
    server_id, camera_num = camera_address.split(":", 1)
    if not server_id or not camera_num:
        return None
    return _normalize_camera_num(camera_num)


SECURITYSPY_PLUGINS = {
    "cynical": {
        "filter": "org.cynic.indigo.securityspy.camera",
        "name": "Cynical SecuritySpy",
        "address_parser": parse_cynical_address,
        "device_type_filter": None,
    },
    "flyingdiver": {
        "filter": "com.flyingdiver.indigoplugin.securityspy",
        "name": "Spy Connect",
        "address_parser": parse_flyingdiver_address,
        "device_type_filter": "spyCamera",  # exclude spyServer devices
    },
}


def split_camera_id(camera_id: str) -> Tuple[Optional[str], str]:
    """Split a UI camera ID "plugin_type:camera_num" into its parts.

    Legacy IDs (bare camera numbers from configs that predate multi-plugin
    support) return (None, camera_id).
    """
    if ":" in camera_id:
        plugin_type, camera_num = camera_id.split(":", 1)
        return plugin_type, camera_num
    return None, camera_id
