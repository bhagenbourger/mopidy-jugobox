import logging
from unittest import mock

import pytest

from mopidy_jugobox.nfc import NFC


@pytest.fixture
def logger_mock() -> mock.Mock:
    return mock.Mock(spec=logging.Logger)


@pytest.fixture
def nfc(logger_mock: mock.Mock) -> NFC:
    return NFC(logger_mock)


@pytest.fixture
def mock_board(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    m = mock.Mock()
    monkeypatch.setattr("mopidy_jugobox.nfc.board", m)
    return m


@pytest.fixture
def mock_busio_i2c(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    m = mock.Mock()
    monkeypatch.setattr("mopidy_jugobox.nfc.busio.I2C", m)
    return m


@pytest.fixture
def mock_pn532_i2c(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    m = mock.Mock()
    monkeypatch.setattr("mopidy_jugobox.nfc.PN532_I2C", m)
    return m


def test_setup_success(
    mock_pn532_i2c: mock.Mock,
    mock_board: mock.Mock,
    mock_busio_i2c: mock.Mock,
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
    mock_pn532_i2c: mock.Mock,
    nfc: NFC,
    logger_mock: mock.Mock,
) -> None:
    mock_pn532_i2c.side_effect = Exception("Setup failed")

    assert nfc.setup() is False
    logger_mock.exception.assert_called_once_with("Failed to initialize PN532")


def test_read_uid_no_pn532(nfc: NFC) -> None:
    assert nfc.read_uid() is None


def test_read_uid_success(nfc: NFC) -> None:
    nfc.pn532 = mock.Mock()
    nfc.pn532.read_passive_target.return_value = b"\x01\x02\x03\x04"

    assert nfc.read_uid() == "0x10x20x30x4"
    nfc.pn532.read_passive_target.assert_called_once_with(timeout=0.5)


def test_read_uid_none(nfc: NFC) -> None:
    nfc.pn532 = mock.Mock()
    nfc.pn532.read_passive_target.return_value = None

    assert nfc.read_uid() is None


def test_read_ntag215_content_no_pn532(nfc: NFC) -> None:
    assert nfc.read_ntag215_content() is None


def test_read_ntag215_content_success(nfc: NFC) -> None:
    number_of_expected_call = 2
    nfc.pn532 = mock.Mock()
    # Mocking multiple blocks, second one has null terminator
    nfc.pn532.ntag2xx_read_block.side_effect = [b"test", b"more\x00"]

    assert nfc.read_ntag215_content() == b"testmore"
    assert nfc.pn532.ntag2xx_read_block.call_count == number_of_expected_call
    nfc.pn532.ntag2xx_read_block.assert_any_call(4)
    nfc.pn532.ntag2xx_read_block.assert_any_call(5)


def test_read_ntag215_content_failure(nfc: NFC, logger_mock: mock.Mock) -> None:
    nfc.pn532 = mock.Mock()
    nfc.pn532.ntag2xx_read_block.side_effect = Exception("Read failed")

    assert nfc.read_ntag215_content() is None
    logger_mock.exception.assert_called_once_with("Error reading tag content")


def test_write_ntag215_content_no_pn532(nfc: NFC) -> None:
    assert nfc.write_ntag215_content(b"data") is False


def test_write_ntag215_content_success(nfc: NFC) -> None:
    nfc.pn532 = mock.Mock()
    nfc.pn532.ntag2xx_write_block.return_value = True

    assert nfc.write_ntag215_content(b"data") is True
    nfc.pn532.ntag2xx_write_block.assert_called_once_with(4, b"data")


def test_write_ntag215_content_failure(nfc: NFC, logger_mock: mock.Mock) -> None:
    nfc.pn532 = mock.Mock()
    nfc.pn532.ntag2xx_write_block.side_effect = Exception("Write failed")

    assert nfc.write_ntag215_content(b"data") is False
    logger_mock.exception.assert_called_once_with("Error writing tag content")


def test_write_ntag215_content_too_long(nfc: NFC, logger_mock: mock.Mock) -> None:
    data = b"a" * 505
    assert nfc.write_ntag215_content(data) is False
    logger_mock.error.assert_called_once_with("Data length exceeds 504 bytes")


def test_write_ntag215_content_success_long_data(nfc: NFC) -> None:
    nfc.pn532 = mock.Mock()
    nfc.pn532.ntag2xx_write_block.return_value = True
    data = b"12345678"
    expected_count = 2

    assert nfc.write_ntag215_content(data) is True
    assert nfc.pn532.ntag2xx_write_block.call_count == expected_count
    nfc.pn532.ntag2xx_write_block.assert_any_call(4, b"1234")
    nfc.pn532.ntag2xx_write_block.assert_any_call(5, b"5678")


def test_write_ntag215_content_padding(nfc: NFC) -> None:
    nfc.pn532 = mock.Mock()
    nfc.pn532.ntag2xx_write_block.return_value = True
    data = b"123"

    assert nfc.write_ntag215_content(data) is True
    nfc.pn532.ntag2xx_write_block.assert_called_once_with(4, b"123\x00")
