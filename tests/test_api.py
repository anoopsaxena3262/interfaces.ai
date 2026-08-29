from fastapi.testclient import TestClient

from interfaces_ai.api.app import create_app


def test_health_and_institution_list() -> None:
    client = TestClient(create_app())
    assert client.get("/health").json()["ok"] is True
    names = {row["id"] for row in client.get("/api/v1/institutions").json()}
    assert names == {"redwood", "northstar", "calloway"}
