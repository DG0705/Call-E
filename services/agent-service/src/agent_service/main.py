"""FastAPI application for the agent-service service."""

from call_e_shared import create_app


app = create_app("agent-service")
