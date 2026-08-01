import json
import logging
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from mopidy.core import Core
from mopidy.models import TlTrack, Track
from mopidy.types import TracklistId, Uri

from mopidy_jugobox.music import Music, MusicConfigError
from mopidy_jugobox.state import State

exepected_time_position = 10000


@pytest.fixture
def core_mock() -> mock.Mock:
    mock_core = mock.Mock(spec=Core)
    mock_core.tracklist = mock.Mock()
    mock_core.playback = mock.Mock()
    return mock_core


@pytest.fixture
def logger_mock() -> mock.Mock:
    return mock.Mock(spec=logging.Logger)


@pytest.fixture
def temp_config_file() -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_path = Path(f.name)
        json.dump({"test_id": ["local:track:1.mp3"]}, f)
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_state_file() -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_path = Path(f.name)
        f.write("{}")
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def state_instance(temp_state_file: Path) -> State:
    return State(str(temp_state_file))


def test_play_music_id_config_not_found(
    core_mock: mock.Mock,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, "non_existent.json", state_instance, logger_mock)
    with pytest.raises(MusicConfigError, match="Config file not found"):
        music.play_music_id("test_id")


def test_play_music_id_config_empty(
    core_mock: mock.Mock, state_instance: State, logger_mock: mock.Mock
) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{}")
        temp_path = Path(f.name)
    try:
        music = Music(core_mock, str(temp_path), state_instance, logger_mock)
        with pytest.raises(MusicConfigError, match="corrupted or empty"):
            music.play_music_id("test_id")
    finally:
        temp_path.unlink()


def test_play_music_id_id_not_found(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    with pytest.raises(MusicConfigError, match="not found in"):
        music.play_music_id("unknown_id")


def test_play_music_id_success(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    music.play_music_id("test_id")

    core_mock.tracklist.clear.assert_called_once()
    core_mock.tracklist.add.assert_called_once()
    called_uris = core_mock.tracklist.add.call_args.kwargs["uris"]
    assert len(called_uris) == 1
    assert called_uris[0] == "local:track:1.mp3"

    core_mock.playback.play.assert_called_once()


def test_play_uris(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    number_of_uris_expected = 2
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    uris = ["local:track:1.mp3", "local:track:2.mp3"]
    music.play_uris(uris)

    core_mock.tracklist.clear.assert_called_once()
    core_mock.tracklist.add.assert_called_once()
    called_uris = core_mock.tracklist.add.call_args.kwargs["uris"]
    assert len(called_uris) == number_of_uris_expected
    assert called_uris[0] == "local:track:1.mp3"
    assert called_uris[1] == "local:track:2.mp3"
    core_mock.playback.play.assert_called_once()


def test_pause(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    music.pause(None)
    core_mock.playback.pause.assert_called_once()


def test_save_new_file(
    core_mock: mock.Mock, state_instance: State, logger_mock: mock.Mock
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "new_config.json"
        music = Music(core_mock, str(config_path), state_instance, logger_mock)
        music.save("new_id", ["uri1", "uri2"])

        assert config_path.exists()
        with config_path.open() as f:
            data = json.load(f)
            assert data == {"new_id": ["uri1", "uri2"]}


def test_save_existing_file(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    music.save("test_id", ["new_uri"])

    with temp_config_file.open() as f:
        data = json.load(f)
        assert data == {"test_id": ["new_uri"]}


def test_save_and_resume_state(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    tl_track = TlTrack(TracklistId(1), Track(uri=Uri("uri2")))
    tl_tracks: list[TlTrack] = [mock.Mock(), tl_track, mock.Mock()]
    uris: list[str] = ["uri1", "uri2", "uri3"]
    core_mock.playback.get_current_tl_track.return_value = tl_track
    core_mock.tracklist.index.return_value = 1
    core_mock.tracklist.add.return_value = tl_tracks
    core_mock.playback.get_time_position.return_value = exepected_time_position

    music.pause("test_uid")

    # Verify state is written to file via State class
    state = state_instance.get("test_uid")
    assert state is not None
    assert state.index == 1
    assert state.time_position == exepected_time_position

    music.play_uris(uris, music_id="test_uid")

    core_mock.playback.play.assert_called_with(tlid=tl_tracks[1].tlid)
    core_mock.playback.seek.assert_called_with(time_position=exepected_time_position)


def test_clear_state(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    uid: str = "test_uid"
    tl_track = TlTrack(TracklistId(1), Track(uri=Uri("uri2")))
    tl_tracks: list[TlTrack] = [mock.Mock(), tl_track, mock.Mock()]
    uris: list[str] = ["uri1", "uri2", "uri3"]
    core_mock.playback.get_current_tl_track.return_value = tl_track
    core_mock.tracklist.index.return_value = 1
    core_mock.tracklist.add.return_value = tl_tracks
    core_mock.playback.get_time_position.return_value = exepected_time_position

    music.pause(uid)
    music.clear_state(uid)
    music.play_uris(uris, music_id=uid)

    core_mock.playback.play.assert_called_with()
    core_mock.playback.seek.assert_not_called()


def test_clear_full_state(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    uid1 = "test_uid1"
    uid2 = "test_uid2"

    # Set up states via State instance directly or via music (delegated)
    state_instance.save(uid1, 1, 100)
    state_instance.save(uid2, 2, 200)

    music.clear_full_state()

    assert len(state_instance.get_all()) == 0


def test_get_states(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    uid = "test_uid"
    state_instance.save(uid, 1, exepected_time_position)

    states = music.get_states()
    assert uid in states
    assert states[uid].index == 1
    assert states[uid].time_position == exepected_time_position


def test_resume_with_invalid_index(
    core_mock: mock.Mock,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, "dummy_path", state_instance, logger_mock)

    uris = ["uri1"]
    new_tl_tracks = [mock.Mock()]
    core_mock.tracklist.add.return_value = new_tl_tracks

    music.play_uris(uris, music_id="test_uid")

    core_mock.playback.play.assert_called_with()


def test_pause_clears_state_when_playback_stopped(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    uid = "test_uid"
    state_instance.save(uid, 0, 1000)
    core_mock.playback.get_current_tl_track.return_value = None

    music.pause(uid)

    assert state_instance.get(uid) is None


def test_pause_clears_state_when_song_finished(
    core_mock: mock.Mock,
    temp_config_file: Path,
    state_instance: State,
    logger_mock: mock.Mock,
) -> None:
    music = Music(core_mock, str(temp_config_file), state_instance, logger_mock)
    uid = "test_uid"
    state_instance.save(uid, 0, 1000)

    track_mock = mock.Mock()
    track_mock.length = 180000
    tl_track = mock.Mock()
    tl_track.track = track_mock

    core_mock.playback.get_current_tl_track.return_value = tl_track
    core_mock.tracklist.index.return_value = 0
    core_mock.playback.get_time_position.return_value = 179500

    music.pause(uid)

    assert state_instance.get(uid) is None
