"""FastAPI application for the agent-service service."""

from call_e_shared import create_app, load_settings


settings = load_settings(default_service_name="agent-service")
app = create_app(settings)
