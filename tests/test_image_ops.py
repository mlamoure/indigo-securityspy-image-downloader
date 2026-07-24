"""Tests for securityspy_image.image_ops — real PIL against temp images."""

import pytest
from PIL import Image

from securityspy_image import image_ops
from securityspy_image.exceptions import ImageProcessingError


def _make_image_file(path, size=(100, 50), color="red"):
    Image.new("RGB", size, color=color).save(path)
    return str(path)


class TestStitchVertical:
    def test_stacks_images_vertically(self):
        images = [
            Image.new("RGB", (100, 50), color="red"),
            Image.new("RGB", (100, 50), color="blue"),
            Image.new("RGB", (150, 50), color="green"),
        ]
        result = image_ops.stitch_vertical(images)
        assert result.size == (150, 150)

    def test_empty_list_gives_empty_canvas(self):
        assert image_ops.stitch_vertical([]).size == (0, 0)


class TestLoadImage:
    def test_returns_copy_without_resize(self, tmp_path):
        source = _make_image_file(tmp_path / "img.jpg", size=(200, 100))
        img = image_ops.load_image(source)
        assert img.size == (200, 100)

    def test_bounds_to_max_width(self, tmp_path):
        source = _make_image_file(tmp_path / "img.jpg", size=(200, 100))
        img = image_ops.load_image(source, max_width=150)
        assert img.width <= 150
        assert img.width / img.height == pytest.approx(2.0)

    def test_negative_max_width_means_no_resize(self, tmp_path):
        source = _make_image_file(tmp_path / "img.jpg", size=(200, 100))
        assert image_ops.load_image(source, max_width=-1).size == (200, 100)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ImageProcessingError, match="Error loading image"):
            image_ops.load_image(str(tmp_path / "missing.jpg"))


class TestResizeToWidth:
    def test_resizes_and_keeps_aspect_ratio(self, tmp_path):
        source = _make_image_file(tmp_path / "source.jpg", size=(200, 100))
        dest = str(tmp_path / "resized.jpg")
        image_ops.resize_to_width(source, dest, 150)
        with Image.open(dest) as img:
            assert img.width <= 150
            assert img.width / img.height == pytest.approx(2.0)

    def test_smaller_image_unchanged(self, tmp_path):
        source = _make_image_file(tmp_path / "source.jpg", size=(100, 50))
        dest = str(tmp_path / "resized.jpg")
        image_ops.resize_to_width(source, dest, 150)
        with Image.open(dest) as img:
            assert img.size == (100, 50)

    def test_no_limit_copies_unchanged(self, tmp_path):
        source = _make_image_file(tmp_path / "source.jpg", size=(200, 100))
        dest = str(tmp_path / "resized.jpg")
        image_ops.resize_to_width(source, dest, -1)
        with Image.open(dest) as img:
            assert img.size == (200, 100)

    def test_missing_source_raises(self, tmp_path):
        with pytest.raises(ImageProcessingError, match="Error resizing image"):
            image_ops.resize_to_width(
                str(tmp_path / "missing.jpg"), str(tmp_path / "out.jpg"), 100
            )


class TestSaveAnimatedGif:
    def test_assembles_frames(self, tmp_path):
        frames = [
            Image.new("RGB", (50, 50), color=color)
            for color in ("red", "green", "blue")
        ]
        destination = str(tmp_path / "out.gif")
        image_ops.save_animated_gif(frames, destination)
        with Image.open(destination) as gif:
            assert gif.is_animated
            assert gif.n_frames == 3

    def test_reverse_order(self, tmp_path):
        frames = [Image.new("RGB", (50, 50), color=color) for color in ("red", "blue")]
        destination = str(tmp_path / "out.gif")
        image_ops.save_animated_gif(frames, destination, reverse=True)
        with Image.open(destination) as gif:
            first_frame = gif.convert("RGB")
            r, g, b = first_frame.getpixel((25, 25))
            assert b > 200 and r < 100  # blue frame plays first

    def test_no_frames_raises(self, tmp_path):
        with pytest.raises(ImageProcessingError, match="No frames captured"):
            image_ops.save_animated_gif([], str(tmp_path / "out.gif"))
