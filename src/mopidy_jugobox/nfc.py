import json
import logging

import board
import busio
from adafruit_pn532.i2c import PN532_I2C
from mopidy.types import Uri

LOGGER = logging.getLogger(__name__)


class NFC:
    def __init__(self, logger: logging.Logger = LOGGER) -> None:
        self.pn532: PN532_I2C | None = None
        self._logger = logger

    def setup(self) -> bool:
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pn532 = PN532_I2C(i2c, debug=False)

            _, ver, rev, _ = self.pn532.firmware_version
            self._logger.info(f"Found PN532 with firmware version: {ver}.{rev}")

            self.pn532.SAM_configuration()
        except Exception:
            self._logger.exception("Failed to initialize PN532")
            return False
        return True

    def read_uid(self) -> str | None:
        """Scan for a card and return its UID."""
        uid = self.pn532.read_passive_target(timeout=0.5) if self.pn532 else None

        return "".join([hex(i) for i in uid]) if uid else None

    def read_ntag215_content(self) -> list[Uri]:
        """Read the content of an NTAG215 tag.

        Returns:
            The list of URIs on the NFC tag.
        """
        if not self.pn532:
            return []

        try:
            full_content = bytearray()
            # NTAG215 has 135 blocks total,
            # user data starts at block 4 and goes up to 129
            # (126 blocks * 4 bytes = 504 bytes)
            for block_num in range(4, 130):
                block = self.pn532.ntag2xx_read_block(block_num)
                if not block:
                    break
                full_content.extend(block)
                if b"\x00" in block:
                    break

            content_str = full_content.rstrip(b"\x00").decode("utf-8")
            if not content_str:
                return []

            try:
                data = json.loads(content_str)
                if isinstance(data, list):
                    return [Uri(u) for u in data]
                return [Uri(str(data))]
            except json.JSONDecodeError:
                # Not JSON, maybe it's just a single URI string
                return [Uri(content_str)]

        except Exception:
            self._logger.exception("Error reading tag content")
            return []

    def write_ntag215_content(self, uris: list[Uri]) -> bool:
        """Write the URIs to an NTAG215 tag.

        Args:
            uris: List of Mopidy URIs to write.

        Returns:
            True if write was successful, False otherwise.
        """
        data = json.dumps(uris).encode("utf-8")
        max_data_length = 504
        if len(data) > max_data_length:
            self._logger.error("Data length exceeds 504 bytes")
            return False

        if not self.pn532:
            return False

        try:
            # Pad data with \x00 to a multiple of 4
            padding_needed = (4 - (len(data) % 4)) % 4
            padded_data = data + b"\x00" * padding_needed

            for i in range(0, len(padded_data), 4):
                block_number = 4 + (i // 4)
                block_data = padded_data[i : i + 4]
                if not self.pn532.ntag2xx_write_block(block_number, block_data):
                    self._logger.error(f"Failed to write block {block_number}")
                    return False
        except Exception:
            self._logger.exception("Error writing tag content")
            return False

        return True
