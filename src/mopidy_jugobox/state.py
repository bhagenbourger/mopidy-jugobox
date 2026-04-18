import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from mopidy.types import DurationMs

LOGGER = logging.getLogger(__name__)


@dataclass
class PlaybackState:
    index: int
    time_position: DurationMs


class State:
    _instance: "State | None" = None
    _singleton_lock = threading.Lock()

    def __init__(self, state_path: str, logger: logging.Logger = LOGGER) -> None:
        self._state_path = Path(state_path).expanduser()
        self._states: dict[str, PlaybackState] = {}
        self._logger = logger
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Loads playback states from the state file."""
        try:
            self._logger.info(f"Loading state from '{self._state_path}'")
            with self._state_path.open() as f:
                data = json.load(f)
                for uid, state_dict in data.items():
                    self._states[uid] = PlaybackState(**state_dict)
        except (FileNotFoundError, IsADirectoryError, json.JSONDecodeError, TypeError):
            self._logger.warning(
                f"Could not load state from '{self._state_path}'. "
                f"Starting with empty state."
            )

    def _write(self) -> None:
        """Writes the current playback states to the state file."""
        try:
            state_to_save = {uid: asdict(state) for uid, state in self._states.items()}
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            with self._state_path.open("w") as f:
                json.dump(state_to_save, f, indent=4)
        except OSError:
            self._logger.warning(
                f"Could not write to state file at '{self._state_path}'"
            )

    def save(self, music_id: str, index: int, time_position: int) -> None:
        """Saves the current playback state for the given music_id."""
        with self._lock:
            self._states[music_id] = PlaybackState(
                index=index,
                time_position=DurationMs(time_position),
            )
            self._write()

    def get(self, music_id: str) -> PlaybackState | None:
        """Returns the saved playback state for the given music_id."""
        with self._lock:
            return self._states.get(music_id)

    def clear(self, music_id: str) -> None:
        """Clears the saved playback state for the given music_id."""
        with self._lock:
            if music_id in self._states:
                del self._states[music_id]
                self._write()

    def clear_full(self) -> None:
        """Clears all saved playback states."""
        with self._lock:
            self._states.clear()
            self._write()

    def get_all(self) -> dict[str, PlaybackState]:
        """Returns all saved playback states."""
        with self._lock:
            return self._states.copy()

    @classmethod
    def get_instance(cls, state_path: str) -> "State":
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = cls(state_path)
            return cls._instance


def get_state(state_path: str) -> State:
    return State.get_instance(state_path)
