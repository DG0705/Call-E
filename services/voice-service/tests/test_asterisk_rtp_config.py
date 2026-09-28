"""Guards for the Dockerized Asterisk RTP/NAT configuration.

The host softphone cannot route RTP to Asterisk's container IP, so the PJSIP
transport must advertise a host-reachable media address while keeping direct
container addresses for in-network peers. These tests pin that configuration.
"""

import os

REPO_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)


def read_pjsip_conf() -> str:
    path = os.path.join(
        REPO_ROOT,
        "services",
        "voice-service",
        "telephony",
        "asterisk",
        "config",
        "pjsip.conf",
    )
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def transport_section(content: str) -> str:
    lines = content.splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.strip() == "[transport-udp]"
    )
    section: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip().startswith("["):
            break
        stripped = line.strip()
        if stripped and not stripped.startswith(";"):
            section.append(stripped)
    return "\n".join(section)


def test_transport_advertises_host_reachable_media_address() -> None:
    section = transport_section(read_pjsip_conf())

    assert "external_media_address = 127.0.0.1" in section


def test_transport_advertises_host_reachable_signaling_address() -> None:
    # Without external_signaling_address, Contact/Via carry the container IP
    # (e.g. 172.19.0.x), which the host softphone cannot route the INVITE
    # ACK back to. Asterisk then retransmits 200 OK until the INVITE server
    # transaction (Timer H) fires at exactly 32 seconds and ends every call
    # with an Asterisk-originated BYE.
    section = transport_section(read_pjsip_conf())

    assert "external_signaling_address = 127.0.0.1" in section


def test_transport_does_not_classify_docker_gateway_as_local() -> None:
    # Docker source-NATs host-originated SIP to the bridge gateway
    # (172.19.0.1), which any Docker-sized local_net would match — making
    # Asterisk advertise its unroutable container IP in SDP again. No
    # local_net may be present on this transport.
    section = transport_section(read_pjsip_conf())

    assert "local_net" not in section
