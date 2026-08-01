"""API Gateway ASGI entrypoint."""

from api_gateway.app import create_gateway_app


app = create_gateway_app()
