import tempfile
from pathlib import Path

import pytest

from mopidy_jugobox.state import State, get_state

EXPECTED_TIME_POSITION = 1000


@pytest.fixture
def temp_state_file() -> Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        temp_path = Path(f.name)
        f.write("{}")
    yield temp_path
    if temp_path.exists():
        temp_path.unlink()


def test_singleton(temp_state_file: Path) -> None:
    s1 = get_state(str(temp_state_file))
    s2 = get_state(str(temp_state_file))
    assert s1 is s2


def test_save_and_get(temp_state_file: Path) -> None:
    state = get_state(str(temp_state_file))
    state.save("uid1", 1, EXPECTED_TIME_POSITION)

    saved_state = state.get("uid1")
    assert saved_state is not None
    assert saved_state.index == 1
    assert saved_state.time_position == EXPECTED_TIME_POSITION


def test_persistence(temp_state_file: Path) -> None:
    file = temp_state_file
    state = State(str(file))
    state.save("uid1", 1, EXPECTED_TIME_POSITION)

    # Simulate restart by creating a new State instance
    state2 = State(str(file))

    saved_state = state2.get("uid1")
    assert saved_state is not None
    assert saved_state.index == 1
    assert saved_state.time_position == EXPECTED_TIME_POSITION


def test_clear(temp_state_file: Path) -> None:
    state = get_state(str(temp_state_file))
    state.save("uid1", 1, EXPECTED_TIME_POSITION)
    state.clear("uid1")

    assert state.get("uid1") is None


def test_clear_full(temp_state_file: Path) -> None:
    state = get_state(str(temp_state_file))
    state.save("uid1", 1, 1000)
    state.save("uid2", 2, 2000)
    state.clear_full()

    assert len(state.get_all()) == 0


def test_load_corrupted_json(temp_state_file: Path) -> None:
    with temp_state_file.open("w") as f:
        f.write("{invalid json}")

    state = get_state(str(temp_state_file))
    assert len(state.get_all()) == 0
