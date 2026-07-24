"""HTTP image downloading.

The requests session is injectable (`session=`) so tests never touch the
network. Unlike the stdlib-only plugins in this family, `requests` is a hard
runtime dependency here.
"""

import os
import shutil
import tempfile
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import requests
import urllib3
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from .exceptions import DownloadError

REQUEST_TIMEOUT = 30  # seconds


def build_securityspy_image_url(
    base_url: str, camera_num: str, width: Optional[int] = None
) -> str:
    """Build a SecuritySpy still-image URL for a camera number.

    A positive `width` asks SecuritySpy to scale the image server-side
    (aspect ratio preserved), so no local resize is needed.
    """
    url = f"{base_url}/++image?cameraNum={camera_num}"
    if width is not None and width > 0:
        url += f"&width={width}"
    return url


def sanitize_url(url: str) -> str:
    """Strip embedded user:password credentials from a URL for safe logging."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def build_auth(
    auth_type: Optional[str], login: Optional[str], password: Optional[str]
) -> Optional[requests.auth.AuthBase]:
    """Create the requests auth handler for `auth_type` ('basic'/'digest'/None).

    Raises DownloadError for an unsupported type or missing credentials.
    """
    if auth_type in (None, "none"):
        return None
    if auth_type not in ("basic", "digest"):
        raise DownloadError(f"Unsupported authentication type: '{auth_type}'")
    if not login or not password:
        raise DownloadError(f"{auth_type} auth requires both login and password")
    if auth_type == "basic":
        return HTTPBasicAuth(login, password)
    return HTTPDigestAuth(login, password)


def create_temp_file(directory: str, prefix: str, suffix: str = ".jpg") -> str:
    """Create a uniquely named temp file in `directory` and return its path.

    Unique names let concurrent actions target the same folder without
    clobbering each other's intermediate files.
    """
    fd, path = tempfile.mkstemp(prefix=f".{prefix}-", suffix=suffix, dir=directory)
    os.close(fd)
    return path


def download_image(
    url: str,
    save_path: str,
    auth: Optional[requests.auth.AuthBase] = None,
    verify_ssl: bool = False,
    timeout: int = REQUEST_TIMEOUT,
    session=None,
) -> int:
    """Stream `url` to `save_path`; return the saved file size in bytes.

    Raises DownloadError on any network, HTTP, or filesystem failure. Error
    messages never contain URL-embedded credentials.
    """
    if not verify_ssl:
        # Self-signed certs are the norm for SecuritySpy; the user opted out
        # of verification, so don't spam InsecureRequestWarning on every call.
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    http = session if session is not None else requests
    safe_url = sanitize_url(url)
    try:
        with http.get(
            url, stream=True, timeout=timeout, verify=verify_ssl, auth=auth
        ) as response:
            response.raise_for_status()
            with open(save_path, "wb") as f:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, f)
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        raise DownloadError(
            f"HTTP error downloading {safe_url} (status: {status})"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise DownloadError(f"Timeout downloading {safe_url} (>{timeout}s)") from exc
    except requests.exceptions.RequestException as exc:
        detail = str(exc).replace(url, safe_url)
        raise DownloadError(
            f"Connection error downloading {safe_url}: {detail}"
        ) from exc
    except OSError as exc:
        raise DownloadError(f"File system error saving '{save_path}': {exc}") from exc

    return os.path.getsize(save_path)
