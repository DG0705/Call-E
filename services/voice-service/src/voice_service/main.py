"""Voice service ASGI entrypoint."""

from voice_service.app import create_voice_app


app = create_voice_app()
