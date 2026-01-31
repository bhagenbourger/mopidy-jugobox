import pykka

from mopidy import backend

from mopidy_jugobox import library


class JugoboxSpotifyBackend(pykka.ThreadingActor, backend.Backend):

    def __init__(self, config, audio):
        super().__init__()
        self.library = library.JugoboxSpotifyLibraryProvider(backend=self)
        self.playback = backend.PlaybackProvider(audio=audio, backend=self)
