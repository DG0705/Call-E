"""Local-only live provider smoke test (task 14).

Exercises the REAL providers end to end without a phone call:
1. Mongo connectivity (via agent-service in compose network)
2. RabbitMQ connectivity (mgmt port from host)
3. Groq request (minimal generate_response, tool schema attached)
4. Deepgram transcription (generated 8 kHz sine PCM, no phone audio needed)
5. ElevenLabs synthesis (short text -> PCM AudioChunk -> ulaw convertible)
6. Asterisk ARI connectivity (authenticated /ari/endpoints)
7. Kaari agent lookup (seeded tenant/agent/tools/greeting)

Gated: refuses to run without --live AND real credentials in the environment.
Never prints secrets. Never runs in CI (lives under tools/, not tests/).

Usage (PowerShell, repo root, .env loaded with real keys):
    $env:LLM_PROVIDER='groq'
    .venv\\Scripts\\python.exe tools\\smoke_live_providers.py --live
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import os
import struct
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared", "src"))
sys.path.insert(0, os.path.join(ROOT, "services", "agent-service", "src"))
sys.path.insert(0, os.path.join(ROOT, "services", "voice-service", "src"))

RESULTS: list[tuple[str, bool, str]] = []


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


def env_value(name: str, default: str = "") -> str:
    """Read one variable: exported process env wins, repo .env is fallback."""
    value = os.getenv(name, "").strip()
    if value:
        return value
    return _DOTENV_VALUES.get(name, default).strip()


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))


def _http_status_code(exc: BaseException) -> int | None:
    """Walk the exception chain for an HTTP status without touching payloads."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
        current = current.__cause__
    return None


def _elevenlabs_detail(exc: Exception) -> str:
    """Classify ElevenLabs failures without exposing secrets.

    HTTP 402 means the configured voice is not available to the current
    account/API tier (e.g. a library voice on a free account) — an account
    issue, not a missing key or provider bug.
    """
    if _http_status_code(exc) == 402:
        return (
            "ElevenLabs: configured voice is not available to the current "
            "account/API tier"
        )
    return f"{type(exc).__name__}"


def need(*names: str) -> dict[str, str] | None:
    values = {name: env_value(name) for name in names}
    missing = sorted(name for name, value in values.items() if not value)
    return None if missing else values


def compose_exec(service: str, code: str, timeout: int = 60) -> tuple[bool, str]:
    completed = subprocess.run(
        ["docker", "compose", "exec", "-T", service, "python", "-c", code],
        capture_output=True, text=True, timeout=timeout, cwd=ROOT,
    )
    if completed.returncode != 0:
        err = (completed.stderr or "").strip().splitlines()
        return False, err[-1][:200] if err else f"exit {completed.returncode}"
    return True, completed.stdout.strip()[:500]


def sine_pcm_8k(seconds: float = 1.0, freq: float = 440.0) -> bytes:
    samples = [
        int(12000 * math.sin(2 * math.pi * freq * i / 8000))
        for i in range(int(8000 * seconds))
    ]
    return struct.pack(f"<{len(samples)}h", *samples)


async def check_groq() -> None:
    from agent_service.runtime.context import ConversationMessage
    from agent_service.runtime.groq_provider import GroqProvider
    from agent_service.runtime.tools import ToolDefinition

    env = need("GROQ_API_KEY", "GROQ_MODEL")
    if env is None:
        record("Groq request", False, "GROQ_API_KEY/GROQ_MODEL missing")
        return
    provider = GroqProvider(api_key=env["GROQ_API_KEY"], model=env["GROQ_MODEL"])
    try:
        response = await provider.generate_response(
            system_instruction="Reply with exactly: SMOKE-OK",
            messages=[ConversationMessage(role="user", content="ping")],
            tools=[
                ToolDefinition(
                    tool_name="echo_customer_context",
                    description="Echo for smoke test.",
                    version="v1",
                    input_schema={"type": "object"},
                )
            ],
        )
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        record("Groq request", False, f"{type(exc).__name__}")
        return
    record(
        "Groq request",
        response.provider_name == "groq" and bool(response.text),
        f"model={response.model_name} chars={len(response.text)} tools_seen={len(response.tool_calls)}",
    )


async def check_deepgram() -> None:
    from voice_service.audio import AudioChunk
    from voice_service.stt_providers import DeepgramSTTProvider

    env = need("DEEPGRAM_API_KEY")
    if env is None:
        record("Deepgram transcription", False, "DEEPGRAM_API_KEY missing")
        return
    provider = DeepgramSTTProvider(
        api_key=env["DEEPGRAM_API_KEY"],
        model=env_value("DEEPGRAM_MODEL", "nova-2") or "nova-2",
        default_language=env_value("DEEPGRAM_LANGUAGE", "en") or "en",
    )
    try:
        result = await provider.transcribe(
            AudioChunk(data=sine_pcm_8k(), format="pcm", sample_rate=8000)
        )
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        record("Deepgram transcription", False, f"{type(exc).__name__}")
        return
    finally:
        await provider.close()
    record(
        "Deepgram transcription",
        result.provider == "deepgram",
        f"text_chars={len(result.text)} confidence={result.confidence}",
    )


async def check_elevenlabs() -> None:
    from voice_service.audio import encode_ulaw
    from voice_service.tts_providers import ElevenLabsTTSProvider

    env = need("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID")
    if env is None:
        record("ElevenLabs synthesis", False, "ELEVENLABS_API_KEY/VOICE_ID missing")
        return
    provider = ElevenLabsTTSProvider(
        api_key=env["ELEVENLABS_API_KEY"], voice_id=env["ELEVENLABS_VOICE_ID"]
    )
    try:
        result = await provider.synthesize(text="Hello from the Call-E smoke test.")
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        record("ElevenLabs synthesis", False, _elevenlabs_detail(exc))
        return
    finally:
        await provider.close()
    try:
        ulaw = encode_ulaw(result.audio)
        convertible = len(ulaw) == len(result.audio.data) // 2
    except ValueError:
        convertible = False
    record(
        "ElevenLabs synthesis",
        result.provider == "elevenlabs" and bool(result.audio.data) and convertible,
        f"format={result.audio.format} bytes={len(result.audio.data)} ulaw_ok={convertible}",
    )


def check_mongo() -> None:
    ok, out = compose_exec(
        "agent-service",
        "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/agents/ping-db',timeout=15).read().decode()[:200])",
    )
    record("Mongo connectivity", ok, out[:160] if ok else out)


def check_rabbitmq() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:15672/", timeout=5) as response:
            record("RabbitMQ connectivity", response.status == 200, "mgmt :15672")
    except urllib.error.HTTPError as exc:
        record("RabbitMQ connectivity", exc.code == 401, f"HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        record("RabbitMQ connectivity", False, type(exc).__name__)


def check_asterisk() -> None:
    user = env_value("ASTERISK_USERNAME")
    password = env_value("ASTERISK_PASSWORD")
    if not user or not password:
        record("Asterisk connectivity", False, "ASTERISK_USERNAME/PASSWORD missing")
        return
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    request = urllib.request.Request(
        "http://127.0.0.1:8088/ari/endpoints",
        headers={"Authorization": f"Basic {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            record("Asterisk connectivity", response.status == 200, "ARI authenticated")
    except urllib.error.HTTPError as exc:
        record("Asterisk connectivity", False, f"ARI HTTP {exc.code} (check ARI user/password)")
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        record("Asterisk connectivity", False, type(exc).__name__)


def check_kaari() -> None:
    ok, out = compose_exec(
        "agent-service",
        "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/agents/kaari-sales-agent?tenant_id=kaari-planters',timeout=15)); "
        "print(json.dumps({'id':d.get('id'),'tools':d.get('allowed_tools'),'knowledge':d.get('knowledge_sources'),'greeting':bool(d.get('greeting'))}))",
    )
    record("Kaari agent lookup", ok and "kaari-sales-agent" in out, out[:200] if ok else out)


async def main_async() -> int:
    check_mongo()
    check_rabbitmq()
    await check_groq()
    await check_deepgram()
    await check_elevenlabs()
    check_asterisk()
    check_kaari()
    width = max(len(name) for name, _, _ in RESULTS)
    failed = False
    for name, ok, detail in RESULTS:
        failed = failed or not ok
        print(f"{name:<{width}}  {'OK' if ok else 'FAIL'}{(' — ' + detail) if detail else ''}")
    print()
    print("SMOKE:", "OK" if not failed else "FAIL")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live provider smoke test (local only).")
    parser.add_argument("--live", action="store_true", help="Required to run real provider calls.")
    args = parser.parse_args()
    if not args.live:
        print("Refusing to run: pass --live with real credentials in the environment.")
        return 2
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
