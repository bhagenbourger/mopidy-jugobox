import json
import logging
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from mopidy.core import Core

from mopidy_jugobox.music import Music, MusicConfigError


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


def test_music_init(core_mock: mock.Mock, logger_mock: mock.Mock) -> None:
    music = Music(core_mock, logger_mock, "dummy_path")
    assert music.config_path == "dummy_path"


def test_play_config_not_found(core_mock: mock.Mock, logger_mock: mock.Mock) -> None:
    music = Music(core_mock, logger_mock, "non_existent.json")
    with pytest.raises(MusicConfigError, match="Config file not found"):
        music.play("test_id")
    logger_mock.error.assert_called()


def test_play_config_empty(core_mock: mock.Mock, logger_mock: mock.Mock) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{}")
        temp_path = Path(f.name)
    try:
        music = Music(core_mock, logger_mock, str(temp_path))
        with pytest.raises(MusicConfigError, match="corrupted or empty"):
            music.play("test_id")
    finally:
        temp_path.unlink()


def test_play_id_not_found(
    core_mock: mock.Mock, logger_mock: mock.Mock, temp_config_file: Path
) -> None:
    music = Music(core_mock, logger_mock, str(temp_config_file))
    with pytest.raises(MusicConfigError, match="not found in"):
        music.play("unknown_id")


def test_play_success(
    core_mock: mock.Mock, logger_mock: mock.Mock, temp_config_file: Path
) -> None:
    music = Music(core_mock, logger_mock, str(temp_config_file))
    music.play("test_id")

    core_mock.tracklist.clear.assert_called_once()
    core_mock.tracklist.add.assert_called_once()
    # Check if Uri objects are created correctly
    called_uris = core_mock.tracklist.add.call_args.kwargs["uris"]
    assert len(called_uris) == 1
    # Uri is a NewType of str, so it should be a str at runtime
    assert isinstance(called_uris[0], str)
    assert called_uris[0] == "local:track:1.mp3"

    core_mock.playback.play.assert_called_once()


def test_pause(core_mock: mock.Mock, logger_mock: mock.Mock) -> None:
    music = Music(core_mock, logger_mock, "dummy_path")
    music.pause()
    core_mock.playback.pause.assert_called_once()


def test_save_new_file(core_mock: mock.Mock, logger_mock: mock.Mock) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "new_config.json"
        music = Music(core_mock, logger_mock, str(config_path))
        music.save("new_id", ["uri1", "uri2"])

        assert config_path.exists()
        with config_path.open() as f:
            data = json.load(f)
            assert data == {"new_id": ["uri1", "uri2"]}


def test_save_existing_file(
    core_mock: mock.Mock, logger_mock: mock.Mock, temp_config_file: Path
) -> None:
    music = Music(core_mock, logger_mock, str(temp_config_file))
    music.save("test_id", ["new_uri"])

    with temp_config_file.open() as f:
        data = json.load(f)
        assert data == {"test_id": ["new_uri"]}


def test_save_error(core_mock: mock.Mock, logger_mock: mock.Mock) -> None:
    # Use a directory as a config path to trigger OSError
    with tempfile.TemporaryDirectory() as tmpdir:
        music = Music(core_mock, logger_mock, tmpdir)
        music.save("id", ["uri"])
        logger_mock.exception.assert_called_with(
            f"Could not write to config file at '{tmpdir}'"
        )
