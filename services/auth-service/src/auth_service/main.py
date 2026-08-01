"""FastAPI application for the auth-service service."""

from call_e_shared import create_app, load_settings


settings = load_settings(default_service_name="auth-service")
app = create_app(settings)
