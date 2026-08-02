import pytest
from mopidy import core
from pytest_mock import MockerFixture

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
def core_mock(mocker: MockerFixture) -> MockerFixture:
    return mocker.Mock(spec=core.Core)


@pytest.fixture
def music_mock(mocker: MockerFixture) -> MockerFixture:
    return mocker.Mock(spec=Music)


@pytest.fixture
def nfc_mock(mocker: MockerFixture) -> MockerFixture:
    return mocker.Mock(spec=NFC)


def test_on_start_nfc_enabled(
    config: dict,
    core_mock: pytest.FixtureRequest,
    nfc_mock: pytest.FixtureRequest,
    mocker: MockerFixture,
) -> None:
    mocker.patch("mopidy_jugobox.frontend.NFC", return_value=nfc_mock)
    frontend = frontend_lib.JugoboxFrontend(config, core_mock)
    nfc_mock.setup.return_value = True
    frontend.on_start()
    nfc_mock.setup.assert_called_once()
    assert frontend.nfc is nfc_mock


def test_on_start_nfc_disabled(
    config: dict, core_mock: pytest.FixtureRequest, mocker: MockerFixture
) -> None:
    config["jugobox"]["nfc_enabled"] = False
    mock_nfc = mocker.patch("mopidy_jugobox.frontend.NFC")
    frontend = frontend_lib.JugoboxFrontend(config, core_mock)
    frontend.on_start()
    mock_nfc.assert_not_called()
    assert frontend.nfc is None


def test_play_music_from_uid(
    config: dict,
    core_mock: pytest.FixtureRequest,
    music_mock: pytest.FixtureRequest,
    mocker: MockerFixture,
) -> None:
    mocker.patch("mopidy_jugobox.frontend.Music", return_value=music_mock)
    frontend = frontend_lib.JugoboxFrontend(config, core_mock)
    uid = "test_uid"
    frontend.play_music(uid)
    music_mock.play_music_id.assert_called_once_with(uid)


def test_play_music_from_content_list(
    config: dict,
    core_mock: pytest.FixtureRequest,
    music_mock: pytest.FixtureRequest,
    mocker: MockerFixture,
) -> None:
    mocker.patch("mopidy_jugobox.frontend.Music", return_value=music_mock)
    frontend = frontend_lib.JugoboxFrontend(config, core_mock)
    uid = "test_uid"
    uris = ["local:track:1.mp3", "local:track:2.mp3"]
    frontend.play_music(uid, uris)
    music_mock.play_uris.assert_called_once_with(uris, music_id=uid)
    music_mock.play_music_id.assert_not_called()


def test_play_music_from_content_single_uri(
    config: dict,
    core_mock: pytest.FixtureRequest,
    music_mock: pytest.FixtureRequest,
    mocker: MockerFixture,
) -> None:
    mocker.patch("mopidy_jugobox.frontend.Music", return_value=music_mock)
    frontend = frontend_lib.JugoboxFrontend(config, core_mock)
    uid = "test_uid"
    uris = ["local:track:1.mp3"]
    frontend.play_music(uid, uris)
    music_mock.play_uris.assert_called_once_with(uris, music_id=uid)
    music_mock.play_music_id.assert_not_called()


def test_play_music_empty_uris(
    config: dict,
    core_mock: pytest.FixtureRequest,
    music_mock: pytest.FixtureRequest,
    mocker: MockerFixture,
) -> None:
    mocker.patch("mopidy_jugobox.frontend.Music", return_value=music_mock)
    frontend = frontend_lib.JugoboxFrontend(config, core_mock)
    uid = "test_uid"
    frontend.play_music(uid, [])
    music_mock.play_music_id.assert_called_once_with(uid)
    music_mock.play_uris.assert_not_called()


def test_start_scanning_no_card_does_not_pause(
    config: dict,
    core_mock: pytest.FixtureRequest,
    music_mock: pytest.FixtureRequest,
    nfc_mock: pytest.FixtureRequest,
    mocker: MockerFixture,
) -> None:
    mocker.patch("mopidy_jugobox.frontend.Music", return_value=music_mock)
    mocker.patch("time.sleep", side_effect=[None, None, Exception("stop_loop")])
    frontend = frontend_lib.JugoboxFrontend(config, core_mock)
    frontend.nfc = nfc_mock
    nfc_mock.read_uid.return_value = None

    with pytest.raises(Exception, match="stop_loop"):
        frontend.start_scanning()

    music_mock.pause.assert_not_called()


def test_start_scanning_card_scan_and_removal(
    config: dict,
    core_mock: pytest.FixtureRequest,
    music_mock: pytest.FixtureRequest,
    nfc_mock: pytest.FixtureRequest,
    mocker: MockerFixture,
) -> None:
    """
    Sequence of UIDs:
    "uid_1" (scanned),
    "uid_1" (held),
    None (removed),
    None (still absent)
    """
    uid_sequence = ["uid_1", "uid_1", None, None]

    mocker.patch("mopidy_jugobox.frontend.Music", return_value=music_mock)
    mocker.patch(
        "time.sleep",
        side_effect=[None, None, None, Exception("stop_loop")],
    )
    frontend = frontend_lib.JugoboxFrontend(config, core_mock)
    frontend.nfc = nfc_mock
    nfc_mock.read_uid.side_effect = uid_sequence
    nfc_mock.read_ntag215_content.return_value = []

    with pytest.raises(Exception, match="stop_loop"):
        frontend.start_scanning()

    # Should play music once for "uid_1"
    music_mock.play_music_id.assert_called_once_with("uid_1")
    # Should pause music once for "uid_1" on removal
    music_mock.pause.assert_called_once_with("uid_1")
