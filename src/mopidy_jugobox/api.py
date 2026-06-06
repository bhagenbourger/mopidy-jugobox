import logging
from dataclasses import asdict

import tornado.web
from mopidy.core import Core

from mopidy_jugobox.state import get_state

from .music import Music
from .nfc import NFC

LOGGER = logging.getLogger(__name__)


class JugoboxPlayHandler(tornado.web.RequestHandler):
    def initialize(
        self,
        music: Music,
        config: dict,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.music: Music = music
        self.config = config
        self.logger = logger

    async def post(self) -> None:
        try:
            data = tornado.escape.json_decode(self.request.body)
            music_id = data.get("id")
            self.logger.info(f"Received id via HTTP: {music_id}")

            if not music_id:
                self.set_status(400)
                self.write(
                    {
                        "status": "error",
                        "message": "Missing 'id' in request body",
                    }
                )
                return

            if self.config["jugobox"]["nfc_enabled"]:
                nfc = NFC()
                if nfc.setup() and nfc.read_uid():
                    self.logger.info(
                        f"Jugo detected on the box. "
                        f"Ignoring HTTP play request for {music_id}."
                    )
                    self.write(
                        {
                            "status": "ignored",
                            "message": "Jugo detected on the box",
                        }
                    )
                    return

            self.music.play_music_id(music_id)
            msg = f"Playing {music_id}"
            self.write({"status": "ok", "message": msg})

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
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.music: Music = music
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
                nfc = NFC()
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
            self.music.clear_state(id_to_save)
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
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.music: Music = music
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

            nfc = NFC()
            if not nfc.setup():
                self.set_status(500)
                msg = "Failed to initialize NFC reader"
                self.write({"status": "error", "message": msg})
                return

            if nfc.write_ntag215_content(uris):
                uid = nfc.read_uid()
                if uid:
                    self.music.clear_state(uid)
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


class JugoboxClearStateHandler(tornado.web.RequestHandler):
    """This endpoint clears the saved playback state for a Jugo."""

    def initialize(
        self,
        music: Music,
        config: dict,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.music: Music = music
        self.config = config
        self.logger = logger

    async def post(self) -> None:
        try:
            music_id: str | None = None
            if self.request.body:
                data = tornado.escape.json_decode(self.request.body)
                music_id = data.get("id")

            if not music_id:
                # Fallback to current Jugo on the box
                nfc: NFC = NFC()
                if nfc.setup():
                    music_id = nfc.read_uid()

            if not music_id:
                self.set_status(400)
                self.write(
                    {
                        "status": "error",
                        "message": "Missing 'id' and no Jugo detected on the box",
                    }
                )
                return

            self.music.clear_state(music_id)
            self.write(
                {
                    "status": "ok",
                    "message": f"Cleared state for {music_id}",
                }
            )

        except ValueError:
            self.set_status(400)
            self.write({"error": "Invalid JSON format"})
        except Exception as e:
            self.logger.exception("Failed to clear state")
            self.set_status(500)
            self.write({"error": str(e)})


class JugoboxClearFullStateHandler(tornado.web.RequestHandler):
    """This endpoint clears all saved playback states."""

    def initialize(
        self,
        music: Music,
        config: dict,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.music: Music = music
        self.config = config
        self.logger = logger

    async def post(self) -> None:
        try:
            self.music.clear_full_state()
            self.write(
                {
                    "status": "ok",
                    "message": "Cleared all playback states",
                }
            )
        except Exception as e:
            self.logger.exception("Failed to clear full state")
            self.set_status(500)
            self.write({"error": str(e)})


class JugoboxGetStateHandler(tornado.web.RequestHandler):
    """This endpoint retrieves saved playback states."""

    def initialize(
        self,
        music: Music,
        config: dict,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self.music: Music = music
        self.config = config
        self.logger = logger

    async def get(self) -> None:
        try:
            states = self.music.get_states()
            # Convert dataclasses to dicts for JSON serialization
            serialized_states = {k: asdict(v) for k, v in states.items()}
            self.write(serialized_states)
        except Exception as e:
            self.logger.exception("Failed to get states")
            self.set_status(500)
            self.write({"error": str(e)})

    async def post(self) -> None:
        # Same as GET for now as per user request (don't need to specify an id)
        await self.get()


def factory(config: dict, core: Core) -> list[tuple[str, type, dict[str, object]]]:
    state = get_state(config["jugobox"]["state_path"])
    music = Music(
        core,
        config["jugobox"]["config_path"],
        state,
    )
    return [
        (
            r"/play",
            JugoboxPlayHandler,
            {"music": music, "config": config},
        ),
        (
            r"/save-in-config",
            JugoboxSaveInConfigHandler,
            {"music": music, "config": config},
        ),
        (
            r"/save-on-jugo",
            JugoboxSaveOnJugoHandler,
            {"music": music, "config": config},
        ),
        (
            r"/clear-state",
            JugoboxClearStateHandler,
            {"music": music, "config": config},
        ),
        (
            r"/clear-full-state",
            JugoboxClearFullStateHandler,
            {"music": music, "config": config},
        ),
        (
            r"/get-state",
            JugoboxGetStateHandler,
            {"music": music, "config": config},
        ),
    ]
