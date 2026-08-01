"""FastAPI application for the campaign-service service."""

from call_e_shared import create_app, load_settings


settings = load_settings(default_service_name="campaign-service")
app = create_app(settings)
