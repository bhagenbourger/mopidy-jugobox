import json
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

from mopidy.core import Core
from mopidy.types import Uri

if TYPE_CHECKING:
    from collections.abc import Iterable


class MusicConfigError(Exception):
    """Custom exception for music configuration errors."""


class Music:
    def __init__(self, core: Core, logger: Logger, config_path: str) -> None:
        self._core = core
        self._logger = logger
        self.config_path = config_path

    def _read_config(self) -> dict | None:
        """Reads the config file and returns its content as a dictionary.

        Returns:
            dict: The content of the config file.
            None: If the file is not found or is a directory.
            {}: If the file is corrupted (JSONDecodeError).
        """
        try:
            with Path(self.config_path).open() as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except IsADirectoryError:
            return None
        except json.JSONDecodeError:
            return {}

    def play_music_id(self, music_id: str) -> None:
        data = self._read_config()
        if data is None:
            error = f"Config file not found at '{self.config_path}'"
            self._logger.error(error)
            raise MusicConfigError(error)
        if not data:
            error = f"Config file at '{self.config_path}' is corrupted or empty."
            self._logger.error(error)
            raise MusicConfigError(error)

        uid: str = str(music_id)
        raw_uris = data.get(uid)
        if not raw_uris:
            error = f"ID '{uid}' not found in '{self.config_path}'"
            self._logger.error(error)
            raise MusicConfigError(error)

        self._logger.info(f"Playing URIs for id '{uid}': {raw_uris}")
        self.play_uris(raw_uris)

    def play_uris(self, uris: "Iterable[str]") -> None:
        """Plays a list of URIs directly.

        Args:
            uris: An iterable of URI strings to play.
        """
        mopidy_uris: Iterable[Uri] = [Uri(quote(uri, safe=":/")) for uri in uris]
        if self._core.tracklist is not None:
            self._core.tracklist.clear()
            self._core.tracklist.add(uris=mopidy_uris)
        if self._core.playback is not None:
            self._core.playback.play()

    def pause(self) -> None:
        if self._core.playback is not None:
            self._core.playback.pause()

    def save(self, music_id: str, uris: list) -> None:
        data = self._read_config()
        if data is None:
            msg = f"Config file not found at '{self.config_path}'. Creating a new one."
            self._logger.info(msg)
            data = {}
        elif not data:
            msg = f"Config file at '{self.config_path}' is corrupted or empty."
            msg += " It will be overwritten."
            self._logger.info(msg)

        data[music_id] = uris

        try:
            with Path(self.config_path).open("w") as f:
                json.dump(data, f, indent=4)
            self._logger.info(f"Saved '{music_id}' to '{self.config_path}'")
        except OSError:
            msg = f"Could not write to config file at '{self.config_path}'"
            self._logger.exception(msg)
