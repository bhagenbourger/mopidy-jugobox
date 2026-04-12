import json
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
        self.music: Music = Music(core, logger, config["jugobox"]["config_path"])

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
                    content = (
                        self.nfc.read_ntag215_content()
                        if self.nfc is not None
                        else None
                    )
                    if content and any(b != 0 for b in content):
                        self.play_music(uid, content)
                    else:
                        self.play_music(uid)
            else:
                logger.info("No card detected.")
                self.music.pause()
                current_uid = None
            time.sleep(1)

    def play_music(self, uid: str, content: bytes | bytearray | None = None) -> None:
        if content:
            try:
                # Strip nulls and decode
                content_str = content.decode("utf-8").strip("\x00")
                if content_str:
                    try:
                        data = json.loads(content_str)
                        if isinstance(data, list):
                            self.music.play_uris(data)
                        else:
                            self.music.play_uris([str(data)])
                    except json.JSONDecodeError:
                        # Not JSON, maybe it's just a single URI string
                        self.music.play_uris([content_str])
                    return
            except UnicodeDecodeError:
                logger.warning("Failed to decode tag content as UTF-8")

        self.music.play_music_id(uid)

    @override
    def on_stop(self) -> None:
        logger.info("Jugobox frontend stopped.")
        self.music.pause()
