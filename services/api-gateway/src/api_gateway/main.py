"""FastAPI application for the api-gateway service."""

from call_e_shared import create_app, load_settings


settings = load_settings(default_service_name="api-gateway")
app = create_app(settings)
