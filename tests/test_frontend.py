from unittest import mock

import pytest
from mopidy import core

from mopidy_jugobox import frontend as frontend_lib
from mopidy_jugobox.music import Music
from mopidy_jugobox.nfc import NFC


@pytest.fixture
def config() -> dict:
    return {
        "jugobox": {
            "enabled": True,
            "nfc_enabled": True,
            "config_path": "test_jugobox.json",
            "state_path": "test_state.json",
        }
    }


@pytest.fixture
def core_mock() -> mock.Mock:
    return mock.Mock(spec=core.Core)


@pytest.fixture
def music_mock() -> mock.Mock:
    return mock.Mock(spec=Music)


@pytest.fixture
def nfc_mock() -> mock.Mock:
    return mock.Mock(spec=NFC)


def test_on_start_nfc_enabled(
    config: dict, core_mock: mock.Mock, nfc_mock: mock.Mock
) -> None:
    with mock.patch("mopidy_jugobox.frontend.NFC", return_value=nfc_mock):
        frontend = frontend_lib.JugoboxFrontend(config, core_mock)
        nfc_mock.setup.return_value = True
        frontend.on_start()
        nfc_mock.setup.assert_called_once()
        assert frontend.nfc is nfc_mock


def test_on_start_nfc_disabled(config: dict, core_mock: mock.Mock) -> None:
    config["jugobox"]["nfc_enabled"] = False
    with mock.patch("mopidy_jugobox.frontend.NFC") as mock_nfc:
        frontend = frontend_lib.JugoboxFrontend(config, core_mock)
        frontend.on_start()
        mock_nfc.assert_not_called()
        assert frontend.nfc is None


def test_play_music_from_uid(
    config: dict, core_mock: mock.Mock, music_mock: mock.Mock
) -> None:
    with mock.patch("mopidy_jugobox.frontend.Music", return_value=music_mock):
        frontend = frontend_lib.JugoboxFrontend(config, core_mock)
        uid = "test_uid"
        frontend.play_music(uid)
        music_mock.play_music_id.assert_called_once_with(uid)


def test_play_music_from_content_list(
    config: dict, core_mock: mock.Mock, music_mock: mock.Mock
) -> None:
    with mock.patch("mopidy_jugobox.frontend.Music", return_value=music_mock):
        frontend = frontend_lib.JugoboxFrontend(config, core_mock)
        uid = "test_uid"
        uris = ["local:track:1.mp3", "local:track:2.mp3"]
        frontend.play_music(uid, uris)
        music_mock.play_uris.assert_called_once_with(uris, music_id=uid)
        music_mock.play_music_id.assert_not_called()


def test_play_music_from_content_single_uri(
    config: dict, core_mock: mock.Mock, music_mock: mock.Mock
) -> None:
    with mock.patch("mopidy_jugobox.frontend.Music", return_value=music_mock):
        frontend = frontend_lib.JugoboxFrontend(config, core_mock)
        uid = "test_uid"
        uris = ["local:track:1.mp3"]
        frontend.play_music(uid, uris)
        music_mock.play_uris.assert_called_once_with(uris, music_id=uid)
        music_mock.play_music_id.assert_not_called()


def test_play_music_empty_uris(
    config: dict, core_mock: mock.Mock, music_mock: mock.Mock
) -> None:
    with mock.patch("mopidy_jugobox.frontend.Music", return_value=music_mock):
        frontend = frontend_lib.JugoboxFrontend(config, core_mock)
        uid = "test_uid"
        frontend.play_music(uid, [])
        music_mock.play_music_id.assert_called_once_with(uid)
        music_mock.play_uris.assert_not_called()
