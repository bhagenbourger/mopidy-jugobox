import logging
import time
from typing import override

import pykka
from mopidy import core

from .music import Music
from .nfc import NFC

logger = logging.getLogger(__name__)


class JugoboxFrontend(pykka.ThreadingActor, core.CoreListener):
    def __init__(self, config: dict, core: core.Core) -> None:
        super().__init__()
        self.core = core
        self.config = config
        self.nfc: NFC | None = None
        self.music: Music = Music(logger, config["jugobox"]["config_path"])

    @override
    def on_start(self) -> None:
        if not self.config["jugobox"]["nfc_enabled"]:
            logger.info("NFC is disabled.")
            return

        self.nfc = NFC(logger)
        if self.nfc.setup():
            self.actor_ref.proxy().start_scanning()

    def start_scanning(self) -> None:
        current_uid = None
        while True:
            uid = self.nfc.read_uid() if self.nfc else None
            if uid:
                if uid != current_uid:
                    current_uid = uid
                    logger.info(f"Card scanned with UID: {uid}")
                    self.play_music(uid)
            else:
                logger.info("No card detected.")
                self.music.pause(self.core)
                current_uid = None
            time.sleep(1)

    def play_music(self, uid: str) -> None:
        self.music.play(self.core, uid)

    @override
    def on_stop(self) -> None:
        logger.info("Jugobox frontend stopped.")
        self.music.pause(self.core)
