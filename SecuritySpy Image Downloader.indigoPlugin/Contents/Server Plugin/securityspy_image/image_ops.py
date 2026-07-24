"""Pure-PIL image operations: stitching, resizing, and GIF assembly."""

from typing import List

from PIL import Image

from .exceptions import ImageProcessingError

# PIL's thumbnail() needs a bounding box; height is effectively unbounded.
THUMBNAIL_MAX_HEIGHT = 100_000
# Playback speed of assembled GIFs (independent of the capture interval).
GIF_PLAYBACK_FRAME_MS = 300
GIF_LOOP_FOREVER = 0


def stitch_vertical(images: List[Image.Image]) -> Image.Image:
    """Stack images vertically onto a canvas as wide as the widest input."""
    result_width = max((image.size[0] for image in images), default=0)
    result_height = sum(image.size[1] for image in images)

    result = Image.new("RGB", (result_width, result_height))
    cur_height = 0
    for image in images:
        result.paste(im=image, box=(0, cur_height))
        cur_height += image.size[1]
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
