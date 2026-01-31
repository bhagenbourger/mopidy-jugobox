import http
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

import pytest
import tornado.web
from mopidy import core
from tornado.httpclient import AsyncHTTPClient

from mopidy_jugobox import api as jugobox_api
from mopidy_jugobox.music import Music


@pytest.fixture
def test_config() -> Iterator[dict]:
    test_data = {
        "test_id": ["local:track:sounds/track1.mp3", "local:track:sounds/track2.mp3"],
        "12": ["local:track:sounds/track12.mp3"],
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


@pytest.fixture
def app(
    test_config: dict, core_mock_http: mock.Mock, music_mock_http: mock.Mock
) -> tornado.web.Application:
    with mock.patch("mopidy_jugobox.api.Music", return_value=music_mock_http):
        handlers = jugobox_api.factory(test_config, core_mock_http)
        return tornado.web.Application(handlers)


@pytest.mark.gen_test
async def test_play_endpoint(
    http_client: AsyncHTTPClient,
    base_url: str,
    music_mock_http: mock.Mock,
    core_mock_http: mock.Mock,
) -> None:
    body = {"id": "test_id"}
    response = await http_client.fetch(
        f"{base_url}/play",
        method="POST",
        body=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    assert response.code == http.HTTPStatus.OK
    assert json.loads(response.body) == {"status": "ok", "message": "Playing test_id"}
    music_mock_http.play.assert_called_once_with(core_mock_http, "test_id")


@pytest.mark.gen_test
async def test_play_handler_post_missing_id(
    http_client: AsyncHTTPClient, base_url: str
) -> None:
    body = {}
    with pytest.raises(tornado.httpclient.HTTPClientError) as e:
        await http_client.fetch(
            f"{base_url}/play",
            method="POST",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
    assert e.value.code == http.HTTPStatus.BAD_REQUEST
    assert json.loads(e.value.response.body) == {
        "status": "error",
        "message": "Missing 'id' in request body",
    }


@pytest.mark.gen_test
async def test_play_handler_post_invalid_json(
    http_client: AsyncHTTPClient, base_url: str
) -> None:
    body = "this is not json"
    with pytest.raises(tornado.httpclient.HTTPClientError) as e:
        await http_client.fetch(
            f"{base_url}/play",
            method="POST",
            body=body,
            headers={"Content-Type": "application/json"},
        )
    assert e.value.code == http.HTTPStatus.BAD_REQUEST
    assert json.loads(e.value.response.body) == {"error": "Invalid JSON format"}


@pytest.mark.gen_test
async def test_save_handler_post_nfc_enabled_uid_found(
    http_client: AsyncHTTPClient,
    base_url: str,
    music_mock_http: mock.Mock,
    test_config: dict,
) -> None:
    test_config["jugobox"]["nfc_enabled"] = True
    body = {"uris": ["local:track:test.mp3"]}
    mock_nfc_instance = mock.Mock()
    mock_nfc_instance.setup.return_value = True
    mock_nfc_instance.read_uid.return_value = "test_uid"

    with mock.patch("mopidy_jugobox.api.NFC", return_value=mock_nfc_instance):
        response = await http_client.fetch(
            f"{base_url}/save",
            method="POST",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
    assert response.code == http.HTTPStatus.OK
    assert json.loads(response.body) == {
        "status": "ok",
        "message": "Saved URIs for ID: test_uid",
    }
    music_mock_http.save.assert_called_once_with("test_uid", ["local:track:test.mp3"])


@pytest.mark.gen_test
async def test_save_handler_post_nfc_enabled_uid_not_found(
    http_client: AsyncHTTPClient, base_url: str, test_config: dict
) -> None:
    test_config["jugobox"]["nfc_enabled"] = True
    body = {"uris": ["local:track:test.mp3"]}
    mock_nfc_instance = mock.Mock()
    mock_nfc_instance.setup.return_value = True
    mock_nfc_instance.read_uid.return_value = None  # Simulate no UID found

    with (
        mock.patch("mopidy_jugobox.api.NFC", return_value=mock_nfc_instance),
        pytest.raises(tornado.httpclient.HTTPClientError) as e,
    ):
        await http_client.fetch(
            f"{base_url}/save",
            method="POST",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
    assert e.value.code == http.HTTPStatus.BAD_REQUEST
    assert json.loads(e.value.response.body) == {
        "status": "error",
        "message": "No NFC tag detected",
    }


@pytest.mark.gen_test
async def test_save_handler_post_nfc_enabled_nfc_setup_fails(
    http_client: AsyncHTTPClient, base_url: str, test_config: dict
) -> None:
    test_config["jugobox"]["nfc_enabled"] = True
    body = {"uris": ["local:track:test.mp3"]}
    mock_nfc_instance = mock.Mock()
    mock_nfc_instance.setup.return_value = False  # Simulate NFC setup failure

    with (
        mock.patch("mopidy_jugobox.api.NFC", return_value=mock_nfc_instance),
        pytest.raises(tornado.httpclient.HTTPClientError) as e,
    ):
        await http_client.fetch(
            f"{base_url}/save",
            method="POST",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
    assert e.value.code == http.HTTPStatus.INTERNAL_SERVER_ERROR
    assert json.loads(e.value.response.body) == {
        "status": "error",
        "message": "Failed to initialize NFC reader",
    }


@pytest.mark.gen_test
async def test_save_handler_post_nfc_disabled_id_provided(
    http_client: AsyncHTTPClient,
    base_url: str,
    music_mock_http: mock.Mock,
    test_config: dict,
) -> None:
    test_config["jugobox"]["nfc_enabled"] = False
    body = {"uris": ["local:track:test.mp3"], "id": "manual_id"}

    response = await http_client.fetch(
        f"{base_url}/save",
        method="POST",
        body=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    assert response.code == http.HTTPStatus.OK
    assert json.loads(response.body) == {
        "status": "ok",
        "message": "Saved URIs for ID: manual_id",
    }
    music_mock_http.save.assert_called_once_with("manual_id", ["local:track:test.mp3"])


@pytest.mark.gen_test
async def test_save_handler_post_nfc_disabled_id_provided_int(
    http_client: AsyncHTTPClient,
    base_url: str,
    music_mock_http: mock.Mock,
    test_config: dict,
) -> None:
    test_config["jugobox"]["nfc_enabled"] = False
    body = {"uris": ["local:track:test.mp3"], "id": 123}  # Integer ID

    response = await http_client.fetch(
        f"{base_url}/save",
        method="POST",
        body=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    assert response.code == http.HTTPStatus.OK
    assert json.loads(response.body) == {
        "status": "ok",
        "message": "Saved URIs for ID: 123",
    }
    music_mock_http.save.assert_called_once_with("123", ["local:track:test.mp3"])


@pytest.mark.gen_test
async def test_save_handler_post_nfc_disabled_id_missing(
    http_client: AsyncHTTPClient, base_url: str, test_config: dict
) -> None:
    test_config["jugobox"]["nfc_enabled"] = False
    body = {"uris": ["local:track:test.mp3"]}  # No 'id' in body

    with pytest.raises(tornado.httpclient.HTTPClientError) as e:
        await http_client.fetch(
            f"{base_url}/save",
            method="POST",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
    assert e.value.code == http.HTTPStatus.BAD_REQUEST
    assert json.loads(e.value.response.body) == {
        "status": "error",
        "message": "NFC is disabled, 'id' parameter is required",
    }


@pytest.mark.gen_test
async def test_save_handler_post_missing_uris(
    http_client: AsyncHTTPClient, base_url: str
) -> None:
    body = {"id": "test_id"}  # Missing 'uris'

    with pytest.raises(tornado.httpclient.HTTPClientError) as e:
        await http_client.fetch(
            f"{base_url}/save",
            method="POST",
            body=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
    assert e.value.code == http.HTTPStatus.BAD_REQUEST
    assert json.loads(e.value.response.body) == {
        "status": "error",
        "message": "Missing 'uris' in request body",
    }


@pytest.mark.gen_test
async def test_save_handler_post_invalid_json(
    http_client: AsyncHTTPClient, base_url: str
) -> None:
    body = "this is not json"
    with pytest.raises(tornado.httpclient.HTTPClientError) as e:
        await http_client.fetch(
            f"{base_url}/save",
            method="POST",
            body=body,
            headers={"Content-Type": "application/json"},
        )
    assert e.value.code == http.HTTPStatus.BAD_REQUEST
    assert json.loads(e.value.response.body) == {"error": "Invalid JSON format"}
