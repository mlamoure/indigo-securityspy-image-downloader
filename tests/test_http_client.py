"""Tests for securityspy_image.http_client — all HTTP goes through FakeSession."""

import os

import pytest
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from conftest import FakeResponse, FakeSession
from securityspy_image import http_client
from securityspy_image.exceptions import DownloadError


class TestBuildSecuritySpyImageUrl:
    def test_builds_url(self):
        url = http_client.build_securityspy_image_url("http://host:8000", "5")
        assert url == "http://host:8000/++image?cameraNum=5"


class TestSanitizeUrl:
    def test_strips_credentials(self):
        url = "http://user:secret@host/img.jpg?x=1"
        assert http_client.sanitize_url(url) == "http://host/img.jpg?x=1"

    def test_no_credentials_unchanged(self):
        url = "https://host:8000/++image?cameraNum=1"
        assert http_client.sanitize_url(url) == url

    def test_garbage_returned_as_is(self):
        assert http_client.sanitize_url("not a url") == "not a url"


class TestBuildAuth:
    def test_basic(self):
        auth = http_client.build_auth("basic", "user", "pass")
        assert isinstance(auth, HTTPBasicAuth)

    def test_digest(self):
        auth = http_client.build_auth("digest", "user", "pass")
        assert isinstance(auth, HTTPDigestAuth)

    def test_none(self):
        assert http_client.build_auth(None, None, None) is None

    def test_literal_none_string(self):
        assert http_client.build_auth("none", "user", "pass") is None

    def test_unsupported_type_raises(self):
        with pytest.raises(DownloadError, match="Unsupported authentication type"):
            http_client.build_auth("bearer", "user", "pass")

    def test_missing_credentials_raise(self):
        with pytest.raises(DownloadError, match="requires both login and password"):
            http_client.build_auth("basic", None, None)


class TestCreateTempFile:
    def test_unique_paths_in_directory(self, tmp_path):
        first = http_client.create_temp_file(str(tmp_path), "stitch1")
        second = http_client.create_temp_file(str(tmp_path), "stitch1")
        assert first != second
        assert os.path.dirname(first) == str(tmp_path)
        assert first.endswith(".jpg")
        assert os.path.exists(first)


class TestDownloadImage:
    def test_success_writes_file_and_returns_size(self, tmp_path, fake_session):
        save_path = str(tmp_path / "image.jpg")
        size = http_client.download_image(
            "http://host/img.jpg", save_path, session=fake_session
        )
        assert size == len(b"fake-image-bytes")
        with open(save_path, "rb") as f:
            assert f.read() == b"fake-image-bytes"

    def test_verify_ssl_flag_passed_through(self, tmp_path):
        session = FakeSession()
        save_path = str(tmp_path / "image.jpg")
        http_client.download_image(
            "http://host/img.jpg", save_path, verify_ssl=True, session=session
        )
        _, kwargs = session.calls[0]
        assert kwargs["verify"] is True

    def test_verify_disabled_by_default(self, tmp_path, fake_session):
        http_client.download_image(
            "http://host/img.jpg", str(tmp_path / "image.jpg"), session=fake_session
        )
        _, kwargs = fake_session.calls[0]
        assert kwargs["verify"] is False

    def test_auth_passed_through(self, tmp_path, fake_session):
        auth = HTTPBasicAuth("user", "pass")
        http_client.download_image(
            "http://host/img.jpg",
            str(tmp_path / "image.jpg"),
            auth=auth,
            session=fake_session,
        )
        _, kwargs = fake_session.calls[0]
        assert kwargs["auth"] is auth

    def test_http_error_raises_download_error(self, tmp_path):
        session = FakeSession(response=FakeResponse(status_code=404))
        with pytest.raises(DownloadError, match="status: 404"):
            http_client.download_image(
                "http://host/img.jpg", str(tmp_path / "image.jpg"), session=session
            )

    def test_timeout_raises_download_error(self, tmp_path):
        session = FakeSession(exc=requests.exceptions.Timeout())
        with pytest.raises(DownloadError, match="Timeout"):
            http_client.download_image(
                "http://host/img.jpg", str(tmp_path / "image.jpg"), session=session
            )

    def test_connection_error_raises_download_error(self, tmp_path):
        session = FakeSession(exc=requests.exceptions.ConnectionError("refused"))
        with pytest.raises(DownloadError, match="Connection error"):
            http_client.download_image(
                "http://host/img.jpg", str(tmp_path / "image.jpg"), session=session
            )

    def test_unwritable_path_raises_download_error(self, tmp_path, fake_session):
        bad_path = str(tmp_path / "missing-dir" / "image.jpg")
        with pytest.raises(DownloadError, match="File system error"):
            http_client.download_image(
                "http://host/img.jpg", bad_path, session=fake_session
            )

    def test_error_messages_never_leak_credentials(self, tmp_path):
        session = FakeSession(
            exc=requests.exceptions.ConnectionError(
                "cannot reach http://user:secret@host/img.jpg"
            )
        )
        with pytest.raises(DownloadError) as excinfo:
            http_client.download_image(
                "http://user:secret@host/img.jpg",
                str(tmp_path / "image.jpg"),
                session=session,
            )
        assert "secret" not in str(excinfo.value)
