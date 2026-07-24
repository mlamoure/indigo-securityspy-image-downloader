"""Typed exceptions for the securityspy_image package."""


class SecuritySpyImageError(Exception):
    """Base class for all errors raised by the securityspy_image package."""


class DownloadError(SecuritySpyImageError):
    """An image could not be downloaded (auth config, network, HTTP, or disk)."""


class DestinationError(SecuritySpyImageError):
    """The destination path is missing or its directory does not exist."""


class ImageProcessingError(SecuritySpyImageError):
    """A PIL operation (load, resize, stitch, GIF assembly) failed."""
