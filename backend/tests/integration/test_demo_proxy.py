"""BE-10 in the demo profile: Caddy's address is a trusted proxy, so the per-IP limit is live.

Caddy (profile `demo`) sends /auth/* straight to the API over the Compose `backend` network.
The API reads the client IP from X-Forwarded-For only when the direct peer is inside
TRUSTED_PROXY_NETS, so that network's subnet must sit inside them. It is pinned in
docker-compose.yml rather than left to Docker's address pools, which a host can change.
"""

import ipaddress

import yaml
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.login_codes import TRUSTED_PROXY_NETS
from app.config import REPO_ROOT
from app.main import create_app
from tests.conftest import FakeMailer

COMPOSE = REPO_ROOT / "infra" / "docker-compose.yml"


def _caddy_subnets() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    compose = yaml.safe_load(COMPOSE.read_text())
    caddy_networks = compose["services"]["caddy"]["networks"]
    assert caddy_networks == ["backend"], "Caddy must reach the API over `backend` only"
    ipam = compose["networks"]["backend"].get("ipam", {}).get("config", [])
    return [ipaddress.ip_network(c["subnet"]) for c in ipam]


def test_caddy_network_is_pinned_inside_the_trusted_proxy_ranges() -> None:
    subnets = _caddy_subnets()
    assert subnets, "pin networks.backend.ipam.config[].subnet in infra/docker-compose.yml"
    for subnet in subnets:
        assert any(
            subnet.version == net.version and subnet.subnet_of(net)  # type: ignore[arg-type]
            for net in TRUSTED_PROXY_NETS
        ), f"{subnet} is not inside TRUSTED_PROXY_NETS"


def test_per_ip_limit_applies_to_clients_behind_caddy(db: Session, fake_mailer: FakeMailer) -> None:
    # A peer address from the pinned subnet (as Caddy's would be) forwarding one real client.
    caddy_ip = str(next(_caddy_subnets()[0].hosts()) + 9)
    client = TestClient(create_app(), client=(caddy_ip, 50000))
    xff = {"X-Forwarded-For": "203.0.113.9"}
    statuses = [
        client.post("/auth/request-code", json={"email": f"u{i}@btu.test"}, headers=xff).status_code
        for i in range(21)
    ]
    assert statuses == [204] * 20 + [429]
    # A different client behind the same Caddy has its own allowance.
    other = client.post(
        "/auth/request-code",
        json={"email": "other@btu.test"},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert other.status_code == 204
