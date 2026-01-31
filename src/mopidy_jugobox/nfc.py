import logging

import board
import busio
from adafruit_pn532.i2c import PN532_I2C


class NFC:
    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self.pn532: PN532_I2C | None = None

    def setup(self) -> bool:
        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.pn532 = PN532_I2C(i2c, debug=False)

            _, ver, rev, _ = self.pn532.firmware_version
            self.logger.info(f"Found PN532 with firmware version: {ver}.{rev}")

            self.pn532.SAM_configuration()
        except Exception:
            self.logger.exception("Failed to initialize PN532")
            return False
        return True

    def read_uid(self) -> str | None:
        """Scan for a card and return its UID."""
        uid = self.pn532.read_passive_target(timeout=0.5) if self.pn532 else None

        return "".join([hex(i) for i in uid]) if uid else None

    def read_tag_content(self) -> bytes | bytearray | None:
        """Read the content of an NFC tag.

        Returns:
            dict: Contains 'uid' and 'data' keys, or None if no tag found
        """
        try:
            return self.pn532.ntag2xx_read_block(4) if self.pn532 else None
        except Exception:
            self.logger.exception("Error reading tag content")
            return None
