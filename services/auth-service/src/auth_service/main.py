"""Auth service ASGI entrypoint."""

from auth_service.app import create_auth_app


app = create_auth_app()
