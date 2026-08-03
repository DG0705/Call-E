"""Agent service ASGI entrypoint."""

from agent_service.app import create_agent_app


app = create_agent_app()
