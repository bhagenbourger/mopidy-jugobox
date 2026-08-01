import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

from mopidy.core import Core
from mopidy.types import Uri

from .state import State

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mopidy.models import TlTrack

LOGGER = logging.getLogger(__name__)
END_OF_THE_SONG_THRESHOLD_MS = 5000  # 5 second threshold to consider a song as "ended"


class MusicConfigError(Exception):
    """Custom exception for music configuration errors."""


class Music:
    def __init__(
        self,
        core: Core,
        config_path: str,
        state: State,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self._core = core
        self.config_path = Path(config_path).expanduser()
        self._state = state
        self._logger = logger
        self._lock = threading.Lock()

    def _read_config(self) -> dict | None:
        """Reads the config file and returns its content as a dictionary.

        Returns:
            dict: The content of the config file.
            None: If the file is not found or is a directory.
            {}: If the file is corrupted (JSONDecodeError).
        """
        try:
            with self.config_path.open() as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except IsADirectoryError:
            return None
        except json.JSONDecodeError:
            return {}

    def _save_state(self, music_id: str) -> None:
        """Saves the current playback state for the given music_id."""
        if self._core.playback is None or self._core.tracklist is None:
            return

        tl_track = self._core.playback.get_current_tl_track()
        if tl_track is None:
            self.clear_state(music_id)
            return

        index = self._core.tracklist.index(tl_track=tl_track)
        time_position = self._core.playback.get_time_position()

        if index is not None and time_position is not None:
            track_length = (
                tl_track.track.length if tl_track and tl_track.track else None
            )
            if (
                track_length is not None
                and time_position >= track_length - END_OF_THE_SONG_THRESHOLD_MS
            ):
                self.clear_state(music_id)
                return

            self._state.save(
                music_id=music_id,
                index=index,
                time_position=time_position,
            )
            self._logger.info(
                f"Saved state for {music_id}: track {index}, position {time_position}"
            )

    def play_music_id(self, music_id: str) -> None:
        with self._lock:
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
        self.play_uris(raw_uris, music_id=uid)

    def play_uris(self, uris: "Iterable[str]", music_id: str | None = None) -> None:
        """Plays a list of URIs directly.

        Args:
            uris: An iterable of URI strings to play.
            music_id: Optional ID to resume playback from.
        """
        mopidy_uris: Iterable[Uri] = [Uri(quote(uri, safe=":/")) for uri in uris]
        tl_tracks: list[TlTrack] = []
        if self._core.tracklist is not None:
            self._core.tracklist.clear()
            tl_tracks = self._core.tracklist.add(uris=mopidy_uris)

        state = self._state.get(music_id) if music_id else None

        if state and tl_tracks and state.index < len(tl_tracks):
            message = (
                f"Resuming {music_id} at track {state.index}, "
                f"position {state.time_position}"
            )
            self._logger.info(message)
            self._core.playback.play(tlid=tl_tracks[state.index].tlid)
            self._core.playback.seek(time_position=state.time_position)
            return

        if self._core.playback is not None:
            self._core.playback.play()

    def clear_state(self, music_id: str) -> None:
        """Clears the saved playback state for the given music_id."""
        self._state.clear(music_id)
        self._logger.info(f"Cleared state for {music_id}")

    def clear_full_state(self) -> None:
        """Clears all saved playback states."""
        self._state.clear_full()
        self._logger.info("Cleared all playback states")

    def get_states(self) -> dict:
        """Returns all saved playback states."""
        return self._state.get_all()

    def pause(self, music_id: str | None = None) -> None:
        if music_id is not None:
            self._save_state(music_id)
        if self._core.playback is not None:
            self._core.playback.pause()

    def save(self, music_id: str, uris: list) -> None:
        with self._lock:
            data = self._read_config()
            if data is None:
                msg = (
                    f"Config file not found at '{self.config_path}'. "
                    f"Creating a new one."
                )
                self._logger.info(msg)
                data = {}
            elif not data:
                msg = f"Config file at '{self.config_path}' is corrupted or empty."
                msg += " It will be overwritten."
                self._logger.info(msg)

            data[music_id] = uris

            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with self.config_path.open("w") as f:
                    json.dump(data, f, indent=4)
                self._logger.info(f"Saved '{music_id}' to '{self.config_path}'")
            except OSError:
                msg = f"Could not write to config file at '{self.config_path}'"
                self._logger.exception(msg)
