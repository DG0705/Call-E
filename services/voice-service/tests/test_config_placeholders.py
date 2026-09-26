"""Guards that tracked config/example files stay placeholder-only.

Real credentials live exclusively in the untracked local `.env` (and in the
running Asterisk container built from a local override). These tests fail if
a real secret is ever committed to a tracked config or example file.
"""

import os

REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)
ASTERISK_CONFIG_DIR = os.path.join(
    REPO_ROOT, "services", "voice-service", "telephony", "asterisk", "config"
)

SECRET_KEYS = (
    "GROQ_API_KEY",
    "DEEPGRAM_API_KEY",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "ASTERISK_USERNAME",
    "ASTERISK_PASSWORD",
    "MONGO_INITDB_ROOT_PASSWORD",
    "RABBITMQ_DEFAULT_PASS",
)


def read_tracked(relative_path: str) -> str:
    with open(os.path.join(REPO_ROOT, relative_path), encoding="utf-8") as handle:
        return handle.read()


def test_ari_conf_keeps_placeholder_password() -> None:
    content = read_tracked(
        "services/voice-service/telephony/asterisk/config/ari.conf"
    )

    assert "password = CHANGE_ME_ARI_LOCAL_ONLY" in content


def test_pjsip_conf_keeps_placeholder_password() -> None:
    content = read_tracked(
        "services/voice-service/telephony/asterisk/config/pjsip.conf"
    )

    assert "password = CHANGE_ME_LOCAL_ONLY" in content


def test_env_examples_leave_secrets_empty() -> None:
    for relative_path in (
        ".env.example",
        "services/voice-service/.env.example",
        "services/agent-service/.env.example",
    ):
        try:
            content = read_tracked(relative_path)
        except OSError:
            continue
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            if key.strip() in SECRET_KEYS:
                assert value.strip() == "", relative_path + ": " + key.strip()
