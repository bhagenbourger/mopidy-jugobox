import logging
import time
from typing import override

import pykka
from mopidy import core
from mopidy.types import Uri

from .music import Music
from .nfc import NFC
from .state import get_state

LOGGER = logging.getLogger(__name__)


class JugoboxFrontend(pykka.ThreadingActor, core.CoreListener):
    def __init__(self, config: dict, core: core.Core) -> None:
        super().__init__()
        self.core = core
        self.config = config
        self.nfc: NFC | None = None
        self.state = get_state(config["jugobox"]["state_path"])
        self.music: Music = Music(
            core,
            config["jugobox"]["config_path"],
            self.state,
        )

    @override
    def on_start(self) -> None:
        if not self.config["jugobox"]["nfc_enabled"]:
            LOGGER.info("NFC is disabled.")
            return

        self.nfc = NFC()
        if self.nfc.setup():
            self.actor_ref.proxy().start_scanning()

    def start_scanning(self) -> None:
        current_uid = None
        while True:
            uid = self.nfc.read_uid() if self.nfc else None
            if uid:
                if uid != current_uid:
                    current_uid = uid
                    LOGGER.info(f"Card scanned with UID: {uid}")
                    uris = (
                        self.nfc.read_ntag215_content() if self.nfc is not None else []
                    )
                    if uris:
                        self.play_music(uid, uris)
                    else:
                        self.play_music(uid)
            else:
                if current_uid is not None:
                    LOGGER.info(f"Card removed. UID: {current_uid}")
                else:
                    LOGGER.info("No card detected.")
                self.music.pause(current_uid)
                current_uid = None
            time.sleep(1)

    def play_music(self, uid: str, uris: list[Uri] | None = None) -> None:
        if uris:
            self.music.play_uris(uris, music_id=uid)
            return

        self.music.play_music_id(uid)

    @override
    def on_stop(self) -> None:
        LOGGER.info("Jugobox frontend stopped.")
        self.music.pause()
