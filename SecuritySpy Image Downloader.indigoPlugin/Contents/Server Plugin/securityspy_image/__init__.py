"""Indigo-free core logic for the SecuritySpy Image Downloader plugin.

This package never imports `indigo`; plugin.py is the thin adapter that
bridges Indigo callbacks to the functions here.
"""

from . import cameras, http_client, image_ops
from .exceptions import (
    DestinationError,
    DownloadError,
    ImageProcessingError,
    SecuritySpyImageError,
)

__all__ = [
    "cameras",
    "http_client",
    "image_ops",
    "DestinationError",
    "DownloadError",
    "ImageProcessingError",
    "SecuritySpyImageError",
]
