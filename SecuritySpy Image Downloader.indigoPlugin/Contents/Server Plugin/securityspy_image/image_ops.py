"""Pure-PIL image operations: stitching, resizing, and GIF assembly."""

import math
from typing import List

from PIL import Image

from .exceptions import ImageProcessingError

# PIL's thumbnail() needs a bounding box; height is effectively unbounded.
THUMBNAIL_MAX_HEIGHT = 100_000
# Playback speed of assembled GIFs (independent of the capture interval).
GIF_PLAYBACK_FRAME_MS = 300
GIF_LOOP_FOREVER = 0

LAYOUT_VERTICAL = "vertical"
LAYOUT_HORIZONTAL = "horizontal"
LAYOUT_GRID = "grid"
VALID_LAYOUTS = (LAYOUT_VERTICAL, LAYOUT_HORIZONTAL, LAYOUT_GRID)
GRID_COLUMNS = 2


def stitch(images: List[Image.Image], layout: str = LAYOUT_VERTICAL) -> Image.Image:
    """Combine images onto one canvas: stacked, side-by-side, or a 2-column grid."""
    if layout == LAYOUT_VERTICAL:
        return _stitch_vertical(images)
    if layout == LAYOUT_HORIZONTAL:
        return _stitch_horizontal(images)
    if layout == LAYOUT_GRID:
        return _stitch_grid(images)
    raise ImageProcessingError(f"Unknown stitch layout: '{layout}'")


def _stitch_vertical(images: List[Image.Image]) -> Image.Image:
    """Stack images vertically onto a canvas as wide as the widest input."""
    result_width = max((image.size[0] for image in images), default=0)
    result_height = sum(image.size[1] for image in images)

    result = Image.new("RGB", (result_width, result_height))
    cur_height = 0
    for image in images:
        result.paste(im=image, box=(0, cur_height))
        cur_height += image.size[1]
    return result


def _stitch_horizontal(images: List[Image.Image]) -> Image.Image:
    """Place images side by side on a canvas as tall as the tallest input."""
    result_width = sum(image.size[0] for image in images)
    result_height = max((image.size[1] for image in images), default=0)

    result = Image.new("RGB", (result_width, result_height))
    cur_width = 0
    for image in images:
        result.paste(im=image, box=(cur_width, 0))
        cur_width += image.size[0]
    return result


def _stitch_grid(images: List[Image.Image]) -> Image.Image:
    """Arrange images left-to-right, top-to-bottom in a 2-column grid.

    Cells are uniform (max width x max height across all inputs) so mixed
    camera resolutions still align into rows and columns.
    """
    if not images:
        return Image.new("RGB", (0, 0))

    cell_width = max(image.size[0] for image in images)
    cell_height = max(image.size[1] for image in images)
    columns = min(GRID_COLUMNS, len(images))
    rows = math.ceil(len(images) / GRID_COLUMNS)

    result = Image.new("RGB", (columns * cell_width, rows * cell_height))
    for index, image in enumerate(images):
        row, column = divmod(index, GRID_COLUMNS)
        result.paste(im=image, box=(column * cell_width, row * cell_height))
    return result


def load_image(path: str, max_width: int = -1) -> Image.Image:
    """Open an image file and return an in-memory copy.

    When `max_width` is positive the copy is bounded to that width,
    preserving aspect ratio (LANCZOS).
    """
    try:
        with Image.open(path) as img:
            if max_width > 0:
                img.thumbnail(
                    (max_width, THUMBNAIL_MAX_HEIGHT), Image.Resampling.LANCZOS
                )
            return img.copy()
    except (OSError, ValueError) as exc:
        raise ImageProcessingError(f"Error loading image '{path}': {exc}") from exc


def resize_to_width(source_path: str, dest_path: str, max_width: int) -> None:
    """Save `source_path` to `dest_path`, bounded to `max_width` if positive."""
    try:
        with Image.open(source_path) as img:
            if max_width > 0:
                img.thumbnail(
                    (max_width, THUMBNAIL_MAX_HEIGHT), Image.Resampling.LANCZOS
                )
            img.save(dest_path)
    except (OSError, ValueError) as exc:
        raise ImageProcessingError(
            f"Error resizing image '{source_path}': {exc}"
        ) from exc


def save_animated_gif(
    frames: List[Image.Image], destination: str, reverse: bool = False
) -> None:
    """Assemble in-memory frames into an animated GIF at `destination`."""
    if not frames:
        raise ImageProcessingError("No frames captured; cannot create GIF")

    ordered = list(reversed(frames)) if reverse else list(frames)
    try:
        ordered[0].save(
            destination,
            save_all=True,
            append_images=ordered[1:],
            duration=GIF_PLAYBACK_FRAME_MS,
            loop=GIF_LOOP_FOREVER,
        )
    except (OSError, ValueError) as exc:
        raise ImageProcessingError(f"Failed to create animated GIF: {exc}") from exc
