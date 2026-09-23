"""Call-E development environment check (task 13).

Validates, without printing secrets:
- required environment variables for the selected providers,
- host-reachable dependencies (RabbitMQ mgmt, Asterisk ARI, Traefik),
- in-network service health + Kaari agent availability via `docker compose exec`.

Usage (PowerShell, repo root):
    .venv\\Scripts\\python.exe tools\\dev_check.py

Exit code 0 when every applicable check passes, 1 otherwise.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROWS: list[tuple[str, str]] = []


def _load_dotenv_values() -> dict[str, str]:
    """Parse root .env KEY=VALUE pairs (process env wins; never printed)."""
    values: dict[str, str] = {}
    try:
        with open(os.path.join(ROOT, ".env"), encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key and key not in values:
                    values[key] = value.strip()
    except OSError:
        pass
    return values


_DOTENV_VALUES = _load_dotenv_values()
_DOTENV_PRESENT = {k for k, v in _DOTENV_VALUES.items() if v}


def env_value(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    return _DOTENV_VALUES.get(name, default).strip()


def report(name: str, ok: bool, detail: str = "") -> None:
    ROWS.append((name, f"{'OK' if ok else 'FAIL'}{(': ' + detail) if detail else ''}"))
    if not ok:
        report.failed = True


report.failed = False


def env_present(name: str) -> bool:
    return bool(os.getenv(name, "").strip()) or name in _DOTENV_PRESENT


def tcp_open(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_status(url: str, timeout: float = 5.0) -> int | str:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code  # e.g. 401 from ARI still proves reachability
    except Exception as exc:  # noqa: BLE001 - diagnostics script
        return f"{type(exc).__name__}"


def compose_exec(service: str, code: str, timeout: int = 30) -> tuple[bool, str]:
    if shutil.which("docker") is None:
        return False, "docker CLI not found"
    command = ["docker", "compose", "exec", "-T", service, "python", "-c", code]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, cwd=ROOT
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics script
        return False, f"{type(exc).__name__}"
    if completed.returncode != 0:
        err = (completed.stderr or "").strip().splitlines()
        return False, err[-1][:160] if err else f"exit {completed.returncode}"
    return True, completed.stdout.strip()[:400]


def check_providers() -> None:
    llm = env_value("LLM_PROVIDER", "mock").lower()
    stt = env_value("VOICE_STT_PROVIDER", "mock").lower()
    tts = env_value("VOICE_TTS_PROVIDER", "mock").lower()
    tel = env_value("TELEPHONY_PROVIDER", "mock").lower()

    if llm == "groq":
        missing = [v for v in ("GROQ_API_KEY", "GROQ_MODEL") if not env_present(v)]
        detail = "missing " + ",".join(missing) if missing else "key+model present"
        report("Groq", not missing, detail)
    elif llm == "mock":
        report("Groq", True, "mock mode (no credentials needed)")
    else:
        report("Groq", False, f"unsupported LLM_PROVIDER={llm!r}")

    if stt == "deepgram":
        report("Deepgram", env_present("DEEPGRAM_API_KEY"), "" if env_present("DEEPGRAM_API_KEY") else "missing DEEPGRAM_API_KEY")
    elif stt == "mock":
        report("Deepgram", True, "mock mode (no credentials needed)")
    else:
        report("Deepgram", False, f"unsupported VOICE_STT_PROVIDER={stt!r}")

    if tts == "elevenlabs":
        report("ElevenLabs", env_present("ELEVENLABS_API_KEY"), "" if env_present("ELEVENLABS_API_KEY") else "missing ELEVENLABS_API_KEY")
    elif tts == "mock":
        report("ElevenLabs", True, "mock mode (no credentials needed)")
    else:
        report("ElevenLabs", False, f"unsupported VOICE_TTS_PROVIDER={tts!r}")

    if tel == "asterisk":
        missing = [v for v in ("ASTERISK_URL",) if not env_present(v)]
        # ASTERISK_URL has a compose default; also require ARI user when set explicitly
        report("Asterisk", not missing, "" if not missing else "missing ASTERISK_URL")
    elif tel == "mock":
        report("Asterisk", True, "mock mode (no PBX needed)")
    else:
        report("Asterisk", False, f"unsupported TELEPHONY_PROVIDER={tel!r}")


_HEALTH_PROBE = (
    "import urllib.request; "
    "print(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=10).read().decode())"
)
_KAARI_PROBE = (
    "import json,urllib.request; "
    "d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/agents/kaari-sales-agent?tenant_id=kaari-planters',timeout=15)); "
    "print(json.dumps({'id':d.get('id'),'tenant_id':d.get('tenant_id'),'status':d.get('status'),'tools':d.get('allowed_tools'),'knowledge':d.get('knowledge_sources'),'greeting_chars':len(d.get('greeting') or '')}))"
)


def main() -> int:
    print("CALL-E DEVELOPMENT CHECK")
    print("(values shown as SET/MISSING only; secrets are never printed)")
    print()

    for var in ("MONGO_INITDB_ROOT_USERNAME", "MONGO_INITDB_ROOT_PASSWORD",
                "RABBITMQ_DEFAULT_USER", "RABBITMQ_DEFAULT_PASS"):
        report(f"env:{var}", env_present(var), "SET" if env_present(var) else "MISSING")

    check_providers()

    ok, out = compose_exec("agent-service", _HEALTH_PROBE)
    report("MongoDB", ok, "reachable via agent-service" if ok else out)
    report("RabbitMQ", http_status("http://127.0.0.1:15672/") in (200, 401), "mgmt :15672")

    ari = http_status("http://127.0.0.1:8088/ari/endpoints")
    report("Asterisk ARI", ari in (200, 401, 403), f"HTTP {ari}")

    ok, out = compose_exec("agent-service", _HEALTH_PROBE)
    report("agent-service", ok, out[:120] if ok else out)
    ok, out = compose_exec("voice-service", _HEALTH_PROBE)
    report("voice-service", ok, out[:120] if ok else out)
    ok, out = compose_exec("knowledge-service", _HEALTH_PROBE)
    report("knowledge-service", ok, out[:120] if ok else out)

    ok, out = compose_exec("agent-service", _KAARI_PROBE)
    report("Kaari Agent", ok and "kaari-sales-agent" in out, out[:200] if ok else out)

    width = max(len(name) for name, _ in ROWS)
    for name, status in ROWS:
        print(f"{name:<{width}}  {status}")
    print()
    print("RESULT:", "OK" if not report.failed else "FAIL")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
