import http
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest
import tornado.web
from mopidy import core
from tornado.testing import AsyncHTTPTestCase, gen_test

from mopidy_jugobox import api as jugobox_api
from mopidy_jugobox.music import Music


@pytest.fixture
def test_config() -> Iterator[dict]:
    test_data = {
        "test_id": ["local:track:track1.mp3", "local:track:track2.mp3"],
        "12": ["local:track:soundstrack12.mp3"],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        config_path = Path(f.name)
        json.dump(test_data, f)
    try:
        yield {
            "jugobox": {
                "enabled": True,
                "nfc_enabled": True,
                "config_path": str(config_path),
            }
        }
    finally:
        config_path.unlink()


@pytest.fixture
def core_mock_http() -> mock.Mock:
    return mock.Mock(spec=core.Core)


@pytest.fixture
def music_mock_http() -> mock.Mock:
    return mock.Mock(spec=Music)


class TestJugoboxApi(AsyncHTTPTestCase):
    @pytest.fixture(autouse=True)
    def setup_fixtures(
        self,
        test_config: dict,
        core_mock_http: mock.Mock,
        music_mock_http: mock.Mock,
    ) -> None:
        self.test_config = test_config
        self.core_mock_http = core_mock_http
        self.music_mock_http = music_mock_http

    def get_app(self) -> tornado.web.Application:
        with mock.patch("mopidy_jugobox.api.Music", return_value=self.music_mock_http):
            handlers = jugobox_api.factory(self.test_config, self.core_mock_http)
            return tornado.web.Application(handlers)

    @gen_test
    async def test_play_endpoint(self) -> None:
        body = {"id": "test_id"}
        response = await self.http_client.fetch(
            self.get_url("/play"),
            method="POST",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        assert response.code == http.HTTPStatus.OK
        assert json.loads(response.body) == {
            "status": "ok",
            "message": "Playing test_id",
        }
        self.music_mock_http.play.assert_called_once_with("test_id")

    @gen_test
    async def test_play_handler_post_missing_id(self) -> None:
        body = {}
        with pytest.raises(tornado.httpclient.HTTPClientError) as e:
            await self.http_client.fetch(
                self.get_url("/play"),
                method="POST",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
        assert e.value.code == http.HTTPStatus.BAD_REQUEST
        assert json.loads(e.value.response.body) == {
            "status": "error",
            "message": "Missing 'id' in request body",
        }

    @gen_test
    async def test_play_handler_post_invalid_json(self) -> None:
        body = "this is not json"
        with pytest.raises(tornado.httpclient.HTTPClientError) as e:
            await self.http_client.fetch(
                self.get_url("/play"),
                method="POST",
                body=body,
                headers={"Content-Type": "application/json"},
            )
        assert e.value.code == http.HTTPStatus.BAD_REQUEST
        assert json.loads(e.value.response.body) == {"error": "Invalid JSON format"}

    @gen_test
    async def test_save_in_config_handler_post_nfc_enabled_uid_found(self) -> None:
        self.test_config["jugobox"]["nfc_enabled"] = True
        body = {"uris": ["local:track:test.mp3"]}
        mock_nfc_instance = mock.Mock()
        mock_nfc_instance.setup.return_value = True
        mock_nfc_instance.read_uid.return_value = "test_uid"

        with mock.patch("mopidy_jugobox.api.NFC", return_value=mock_nfc_instance):
            response = await self.http_client.fetch(
                self.get_url("/save-in-config"),
                method="POST",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
        assert response.code == http.HTTPStatus.OK
        assert json.loads(response.body) == {
            "status": "ok",
            "message": "Saved URIs for ID: test_uid",
        }
        self.music_mock_http.save.assert_called_once_with(
            "test_uid", ["local:track:test.mp3"]
        )

    @gen_test
    async def test_save_in_config_handler_post_nfc_enabled_uid_not_found(self) -> None:
        self.test_config["jugobox"]["nfc_enabled"] = True
        body = {"uris": ["local:track:test.mp3"]}
        mock_nfc_instance = mock.Mock()
        mock_nfc_instance.setup.return_value = True
        mock_nfc_instance.read_uid.return_value = None  # Simulate no UID found

        with (
            mock.patch("mopidy_jugobox.api.NFC", return_value=mock_nfc_instance),
            pytest.raises(tornado.httpclient.HTTPClientError) as e,
        ):
            await self.http_client.fetch(
                self.get_url("/save-in-config"),
                method="POST",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
        assert e.value.code == http.HTTPStatus.BAD_REQUEST
        assert json.loads(e.value.response.body) == {
            "status": "error",
            "message": "No NFC tag detected",
        }

    @gen_test
    async def test_save_in_config_handler_post_nfc_enabled_nfc_setup_fails(
        self,
    ) -> None:
        self.test_config["jugobox"]["nfc_enabled"] = True
        body = {"uris": ["local:track:test.mp3"]}
        mock_nfc_instance = mock.Mock()
        mock_nfc_instance.setup.return_value = False  # Simulate NFC setup failure

        with (
            mock.patch("mopidy_jugobox.api.NFC", return_value=mock_nfc_instance),
            pytest.raises(tornado.httpclient.HTTPClientError) as e,
        ):
            await self.http_client.fetch(
                self.get_url("/save-in-config"),
                method="POST",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
        assert e.value.code == http.HTTPStatus.INTERNAL_SERVER_ERROR
        assert json.loads(e.value.response.body) == {
            "status": "error",
            "message": "Failed to initialize NFC reader",
        }

    @gen_test
    async def test_save_in_config_handler_post_nfc_disabled_id_provided(self) -> None:
        self.test_config["jugobox"]["nfc_enabled"] = False
        body = {"uris": ["local:track:test.mp3"], "id": "manual_id"}

        response = await self.http_client.fetch(
            self.get_url("/save-in-config"),
            method="POST",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        assert response.code == http.HTTPStatus.OK
        assert json.loads(response.body) == {
            "status": "ok",
            "message": "Saved URIs for ID: manual_id",
        }
        self.music_mock_http.save.assert_called_once_with(
            "manual_id", ["local:track:test.mp3"]
        )

    @gen_test
    async def test_save_in_config_handler_post_nfc_disabled_id_provided_int(
        self,
    ) -> None:
        self.test_config["jugobox"]["nfc_enabled"] = False
        body = {"uris": ["local:track:test.mp3"], "id": 123}  # Integer ID

        response = await self.http_client.fetch(
            self.get_url("/save-in-config"),
            method="POST",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
        assert response.code == http.HTTPStatus.OK
        assert json.loads(response.body) == {
            "status": "ok",
            "message": "Saved URIs for ID: 123",
        }
        self.music_mock_http.save.assert_called_once_with(
            "123", ["local:track:test.mp3"]
        )

    @gen_test
    async def test_save_in_config_handler_post_nfc_disabled_id_missing(self) -> None:
        self.test_config["jugobox"]["nfc_enabled"] = False
        body = {"uris": ["local:track:test.mp3"]}  # No 'id' in body

        with pytest.raises(tornado.httpclient.HTTPClientError) as e:
            await self.http_client.fetch(
                self.get_url("/save-in-config"),
                method="POST",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
        assert e.value.code == http.HTTPStatus.BAD_REQUEST
        assert json.loads(e.value.response.body) == {
            "status": "error",
            "message": "NFC is disabled, 'id' parameter is required",
        }

    @gen_test
    async def test_save_in_config_handler_post_missing_uris(self) -> None:
        body = {"id": "test_id"}  # Missing 'uris'

        with pytest.raises(tornado.httpclient.HTTPClientError) as e:
            await self.http_client.fetch(
                self.get_url("/save-in-config"),
                method="POST",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
        assert e.value.code == http.HTTPStatus.BAD_REQUEST
        assert json.loads(e.value.response.body) == {
            "status": "error",
            "message": "Missing 'uris' in request body",
        }

    @gen_test
    async def test_save_in_config_handler_post_invalid_json(self) -> None:
        body = "this is not json"
        with pytest.raises(tornado.httpclient.HTTPClientError) as e:
            await self.http_client.fetch(
                self.get_url("/save-in-config"),
                method="POST",
                body=body,
                headers={"Content-Type": "application/json"},
            )
        assert e.value.code == http.HTTPStatus.BAD_REQUEST
        assert json.loads(e.value.response.body) == {"error": "Invalid JSON format"}

    @gen_test
    async def test_save_on_jugo_handler_post_success(self) -> None:
        body = {"uris": ["local:track:test.mp3"]}
        mock_nfc_instance = mock.Mock()
        mock_nfc_instance.setup.return_value = True
        mock_nfc_instance.write_ntag215_content.return_value = True

        with mock.patch("mopidy_jugobox.api.NFC", return_value=mock_nfc_instance):
            response = await self.http_client.fetch(
                self.get_url("/save-on-jugo"),
                method="POST",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
        assert response.code == http.HTTPStatus.OK
        assert json.loads(response.body) == {
            "status": "ok",
            "message": "Saved URIs to NFC tag",
        }
        mock_nfc_instance.write_ntag215_content.assert_called_once_with(
            json.dumps(body["uris"]).encode("utf-8")
        )

    @gen_test
    async def test_save_on_jugo_handler_post_nfc_setup_fails(self) -> None:
        body = {"uris": ["local:track:test.mp3"]}
        mock_nfc_instance = mock.Mock()
        mock_nfc_instance.setup.return_value = False

        with (
            mock.patch("mopidy_jugobox.api.NFC", return_value=mock_nfc_instance),
            pytest.raises(tornado.httpclient.HTTPClientError) as e,
        ):
            await self.http_client.fetch(
                self.get_url("/save-on-jugo"),
                method="POST",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
        assert e.value.code == http.HTTPStatus.INTERNAL_SERVER_ERROR
        assert json.loads(e.value.response.body) == {
            "status": "error",
            "message": "Failed to initialize NFC reader",
        }

    @gen_test
    async def test_save_on_jugo_handler_post_write_fails(self) -> None:
        body = {"uris": ["local:track:test.mp3"]}
        mock_nfc_instance = mock.Mock()
        mock_nfc_instance.setup.return_value = True
        mock_nfc_instance.write_ntag215_content.return_value = False

        with (
            mock.patch("mopidy_jugobox.api.NFC", return_value=mock_nfc_instance),
            pytest.raises(tornado.httpclient.HTTPClientError) as e,
        ):
            await self.http_client.fetch(
                self.get_url("/save-on-jugo"),
                method="POST",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
        assert e.value.code == http.HTTPStatus.INTERNAL_SERVER_ERROR
        assert json.loads(e.value.response.body) == {
            "status": "error",
            "message": (
                "Failed to write to NFC tag. Data might be too large (max 504 bytes)."
            ),
        }

    @gen_test
    async def test_save_on_jugo_handler_post_missing_uris(self) -> None:
        body = {}
        with pytest.raises(tornado.httpclient.HTTPClientError) as e:
            await self.http_client.fetch(
                self.get_url("/save-on-jugo"),
                method="POST",
                body=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )
        assert e.value.code == http.HTTPStatus.BAD_REQUEST
        assert json.loads(e.value.response.body) == {
            "status": "error",
            "message": "Missing 'uris' in request body",
        }
