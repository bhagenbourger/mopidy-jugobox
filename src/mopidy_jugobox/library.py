from mopidy import backend
from mopidy.types import Uri
from mopidy.models import Track

class JugoboxSpotifyLibraryProvider(backend.LibraryProvider):

    def __init__(self, backend):
        self._backend = backend

    def lookup_many(self, uris) -> dict[Uri, list[Track]]:
        return {Uri(uri): [Track(uri=uri)] for uri in uris}
