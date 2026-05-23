import pathlib
from importlib.metadata import version
from typing import Any, cast, override

from mopidy import config, ext

from .api import factory
from .frontend import JugoboxFrontend

__version__ = version("mopidy-jugobox")


class Extension(ext.Extension):
    dist_name: str = "mopidy-jugobox"
    ext_name: str = "jugobox"
    version = __version__

    @override
    def get_default_config(self) -> str:
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    @override
    def get_config_schema(self) -> config.ConfigSchema:
        schema = super().get_config_schema()
        schema["nfc_enabled"] = config.Boolean()
        schema["config_path"] = config.Path()
        schema["state_path"] = config.Path()
        return schema

    @override
    def setup(self, registry: ext.Registry) -> None:
        http_app_config: dict[str, Any] = {
            "name": self.ext_name,
            "factory": factory,
        }
        registry.add("frontend", JugoboxFrontend)
        registry.add("http:app", cast("Any", http_app_config))
