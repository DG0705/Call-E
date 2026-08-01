from call_e_shared.config import load_settings


def test_load_settings_uses_environment_overrides(monkeypatch) -> None:
    monkeypatch.setenv("SERVICE_NAME", "configured-service")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("PORT", "9000")

    settings = load_settings(default_service_name="fallback-service")

    assert settings.service_name == "configured-service"
    assert settings.port == 9000
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
