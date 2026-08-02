import json
import logging
from unittest.mock import Mock

import pytest
from mopidy.types import Uri
from pytest_mock import MockerFixture

from mopidy_jugobox.nfc import NFC


@pytest.fixture
def logger_mock(mocker: MockerFixture) -> Mock:
    """Mock a logger used by NFC."""
    return mocker.Mock(spec=logging.Logger)


@pytest.fixture
def mock_board(mocker: MockerFixture) -> Mock:
    """Patch the board module used by NFC and return the mock with SCL/SDA attrs."""
    board = mocker.Mock()
    board.SCL = "SCL"
    board.SDA = "SDA"
    mocker.patch("mopidy_jugobox.nfc.board", board)
    return board


@pytest.fixture
def mock_busio_i2c(mocker: MockerFixture) -> Mock:
    """Patch the busio.I2C class used by NFC and return the mock class."""
    i2c_mock = mocker.Mock()
    mocker.patch("mopidy_jugobox.nfc.busio.I2C", i2c_mock)
    return i2c_mock


@pytest.fixture
def mock_pn532_i2c(mocker: MockerFixture) -> Mock:
    """Patch the PN532_I2C class used by NFC and return the mock class."""
    pn532_mock = mocker.Mock()
    mocker.patch("mopidy_jugobox.nfc.PN532_I2C", pn532_mock)
    return pn532_mock


@pytest.fixture
def nfc(logger_mock: Mock) -> NFC:
    return NFC(logger_mock)


def test_setup_success(
    mock_pn532_i2c: pytest.FixtureRequest,
    mock_board: pytest.FixtureRequest,
    mock_busio_i2c: pytest.FixtureRequest,
    nfc: NFC,
) -> None:
    mock_pn532_instance = mock_pn532_i2c.return_value
    mock_pn532_instance.firmware_version = (1, 2, 3, 4)

    assert nfc.setup() is True

    mock_busio_i2c.assert_called_once_with(mock_board.SCL, mock_board.SDA)
    mock_pn532_i2c.assert_called_once_with(mock_busio_i2c.return_value, debug=False)
    mock_pn532_instance.SAM_configuration.assert_called_once()
    assert nfc.pn532 == mock_pn532_instance


def test_setup_failure(
    mock_pn532_i2c: pytest.FixtureRequest,
    nfc: NFC,
    logger_mock: pytest.FixtureRequest,
) -> None:
    mock_pn532_i2c.side_effect = Exception("Setup failed")

    assert nfc.setup() is False
    logger_mock.exception.assert_called_once_with("Failed to initialize PN532")


def test_read_uid_no_pn532(nfc: NFC) -> None:
    assert nfc.read_uid() is None


def test_read_uid_success(nfc: NFC, mocker: MockerFixture) -> None:
    nfc.pn532 = mocker.Mock()
    nfc.pn532.read_passive_target.return_value = b"\x01\x02\x03\x04"

    assert nfc.read_uid() == "0x10x20x30x4"
    nfc.pn532.read_passive_target.assert_called_once_with(timeout=0.5)


def test_read_uid_none(nfc: NFC, mocker: MockerFixture) -> None:
    nfc.pn532 = mocker.Mock()
    nfc.pn532.read_passive_target.return_value = None

    assert nfc.read_uid() is None


def test_read_ntag215_content_no_pn532(nfc: NFC) -> None:
    assert nfc.read_ntag215_content() == []


def test_read_ntag215_content_success(nfc: NFC, mocker: MockerFixture) -> None:
    block_size: int = 4
    nfc.pn532 = mocker.Mock()
    # Mocking multiple blocks, second one has null terminator
    # JSON list of URIs
    uris = ["local:track:1.mp3", "local:track:2.mp3"]
    content = json.dumps(uris).encode("utf-8")
    blocks = [content[i : i + block_size] for i in range(0, len(content), block_size)]
    if len(blocks[-1]) < block_size:
        blocks[-1] = blocks[-1].ljust(block_size, b"\x00")
    else:
        blocks.append(b"\x00" * block_size)

    nfc.pn532.ntag2xx_read_block.side_effect = blocks

    assert nfc.read_ntag215_content() == [Uri(u) for u in uris]
    assert nfc.pn532.ntag2xx_read_block.call_count == len(blocks)


def test_read_ntag215_content_fallback_single_uri(
    nfc: NFC, mocker: MockerFixture
) -> None:
    nfc.pn532 = mocker.Mock()
    nfc.pn532.ntag2xx_read_block.side_effect = [
        b"loca",
        b"l:tr",
        b"ack:",
        b"1.mp",
        b"3\x00\x00\x00",
    ]

    assert nfc.read_ntag215_content() == [Uri("local:track:1.mp3")]


def test_read_ntag215_content_failure(
    nfc: NFC, logger_mock: pytest.FixtureRequest, mocker: MockerFixture
) -> None:
    nfc.pn532 = mocker.Mock()
    nfc.pn532.ntag2xx_read_block.side_effect = Exception("Read failed")

    assert nfc.read_ntag215_content() == []
    logger_mock.exception.assert_called_once_with("Error reading tag content")


def test_write_ntag215_content_no_pn532(nfc: NFC) -> None:
    assert nfc.write_ntag215_content([Uri("local:track:1.mp3")]) is False


def test_write_ntag215_content_success(nfc: NFC, mocker: MockerFixture) -> None:
    nfc.pn532 = mocker.Mock()
    nfc.pn532.ntag2xx_write_block.return_value = True
    uris = [Uri("local:track:1.mp3")]
    expected_data = json.dumps(uris).encode("utf-8")
    # Pad to multiple of 4
    padding_needed = (4 - (len(expected_data) % 4)) % 4
    expected_data += b"\x00" * padding_needed
    expected_count = len(expected_data) // 4

    assert nfc.write_ntag215_content(uris) is True
    assert nfc.pn532.ntag2xx_write_block.call_count == expected_count
    for i in range(expected_count):
        nfc.pn532.ntag2xx_write_block.assert_any_call(
            4 + i, expected_data[i * 4 : (i + 1) * 4]
        )


def test_write_ntag215_content_failure(
    nfc: NFC, logger_mock: pytest.FixtureRequest, mocker: MockerFixture
) -> None:
    nfc.pn532 = mocker.Mock()
    nfc.pn532.ntag2xx_write_block.side_effect = Exception("Write failed")

    assert nfc.write_ntag215_content([Uri("local:track:1.mp3")]) is False
    logger_mock.exception.assert_called_once_with("Error writing tag content")


def test_write_ntag215_content_too_long(
    nfc: NFC, logger_mock: pytest.FixtureRequest
) -> None:
    uris = [Uri("local:track:" + "a" * 500)]
    assert nfc.write_ntag215_content(uris) is False
    logger_mock.error.assert_called_once_with("Data length exceeds 504 bytes")


def test_write_ntag215_content_with_padding_success(
    nfc: NFC, mocker: MockerFixture
) -> None:
    nfc.pn532 = mocker.Mock()
    nfc.pn532.ntag2xx_write_block.return_value = True
    data = [Uri("local:track:1.mp3")]
    expected_count = 6

    assert nfc.write_ntag215_content(data) is True
    assert nfc.pn532.ntag2xx_write_block.call_count == expected_count
    nfc.pn532.ntag2xx_write_block.assert_any_call(4, b'["lo')
    nfc.pn532.ntag2xx_write_block.assert_any_call(5, b"cal:")
    nfc.pn532.ntag2xx_write_block.assert_any_call(6, b"trac")
    nfc.pn532.ntag2xx_write_block.assert_any_call(7, b"k:1.")
    nfc.pn532.ntag2xx_write_block.assert_any_call(8, b'mp3"')
    nfc.pn532.ntag2xx_write_block.assert_any_call(9, b"]\x00\x00\x00")
