import json
import logging

import tornado.web
from mopidy.core import Core

from .music import Music
from .nfc import NFC

logger = logging.getLogger(__name__)


class JugoboxPlayHandler(tornado.web.RequestHandler):
    def initialize(self, music: Music, logger: logging.Logger) -> None:
        self.music: Music = music
        self.logger = logger

    async def post(self) -> None:
        try:
            data = tornado.escape.json_decode(self.request.body)
            music_id = data.get("id")
            self.logger.info(f"Received id via HTTP: {music_id}")

            if music_id:
                self.music.play(music_id)
                msg = f"Playing {music_id}"
                self.write({"status": "ok", "message": msg})
            else:
                self.set_status(400)
                self.write(
                    {
                        "status": "error",
                        "message": "Missing 'id' in request body",
                    }
                )

        except ValueError:
            self.set_status(400)
            self.write({"error": "Invalid JSON format"})
        except Exception as e:
            self.logger.exception("Failed to play playlist")
            self.set_status(500)
            self.write({"error": str(e)})


class JugoboxSaveInConfigHandler(tornado.web.RequestHandler):
    """
    This endpoint saves music to play by the Jugo into the local configuration file.
    """

    def initialize(
        self,
        music: Music,
        config: dict,
        logger: logging.Logger,
    ) -> None:
        self.music = music
        self.config = config
        self.logger = logger

    async def post(self) -> None:
        try:
            data = tornado.escape.json_decode(self.request.body)
            uris = data.get("uris")
            if not uris:
                self.set_status(400)
                msg = "Missing 'uris' in request body"
                self.write({"status": "error", "message": msg})
                return

            id_to_save: str | None = None
            if self.config["jugobox"]["nfc_enabled"]:
                nfc = NFC(self.logger)
                if not nfc.setup():
                    self.set_status(500)
                    msg = "Failed to initialize NFC reader"
                    self.write({"status": "error", "message": msg})
                    return

                uid = nfc.read_uid()
                if uid:
                    id_to_save = uid
                    self.logger.info(f"NFC tag detected with UID: {uid}")
                else:
                    self.set_status(400)
                    msg = "No NFC tag detected"
                    self.write({"status": "error", "message": msg})
                    return
            else:
                id_from_param = data.get("id")
                if not id_from_param:
                    self.set_status(400)
                    msg = "NFC is disabled, 'id' parameter is required"
                    self.write({"status": "error", "message": msg})
                    return
                id_to_save = str(id_from_param)
                self.logger.info(f"Using provided ID: {id_to_save}")

            self.music.save(id_to_save, uris)
            msg = f"Saved URIs for ID: {id_to_save}"
            self.write({"status": "ok", "message": msg})

        except ValueError:
            self.set_status(400)
            self.write({"error": "Invalid JSON format"})
        except Exception as e:
            self.logger.exception("Failed to save playlist")
            self.set_status(500)
            self.write({"error": str(e)})


class JugoboxSaveOnJugoHandler(tornado.web.RequestHandler):
    """This endpoint saves music to play by the Jugo directly into the NFC tag."""

    def initialize(
        self,
        music: Music,
        config: dict,
        logger: logging.Logger,
    ) -> None:
        self.music = music
        self.config = config
        self.logger = logger

    async def post(self) -> None:
        try:
            data = tornado.escape.json_decode(self.request.body)
            uris = data.get("uris")
            if not uris:
                self.set_status(400)
                msg = "Missing 'uris' in request body"
                self.write({"status": "error", "message": msg})
                return

            nfc = NFC(self.logger)
            if not nfc.setup():
                self.set_status(500)
                msg = "Failed to initialize NFC reader"
                self.write({"status": "error", "message": msg})
                return

            # Convert uris to bytes
            # We use JSON to store the list of URIs
            uris_bytes = json.dumps(uris).encode("utf-8")

            if nfc.write_ntag215_content(uris_bytes):
                msg = "Saved URIs to NFC tag"
                self.write({"status": "ok", "message": msg})
            else:
                self.set_status(500)
                msg = (
                    "Failed to write to NFC tag. "
                    "Data might be too large (max 504 bytes)."
                )
                self.write({"status": "error", "message": msg})

        except ValueError:
            self.set_status(400)
            self.write({"error": "Invalid JSON format"})
        except Exception as e:
            self.logger.exception("Failed to save playlist to NFC")
            self.set_status(500)
            self.write({"error": str(e)})


def factory(config: dict, core: Core) -> list[tuple[str, type, dict[str, object]]]:
    music = Music(core, logger, config["jugobox"]["config_path"])
    return [
        (
            r"/play",
            JugoboxPlayHandler,
            {"music": music, "logger": logger},
        ),
        (
            r"/save-in-config",
            JugoboxSaveInConfigHandler,
            {"music": music, "config": config, "logger": logger},
        ),
        (
            r"/save-on-jugo",
            JugoboxSaveOnJugoHandler,
            {"music": music, "config": config, "logger": logger},
        ),
    ]
