from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_health_uses_success_envelope() -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"success": True, "data": {"ok": True, "version": "0.1.0"}}


def test_unknown_route_uses_error_envelope() -> None:
    res = client.get("/nope")
    assert res.status_code == 404
    assert res.json() == {"success": False, "error": {"code": "not_found", "message": "Not Found"}}


def test_validation_error_envelope() -> None:
    app = create_app()

    @app.get("/echo")
    async def echo(n: int) -> int:
        return n

    res = TestClient(app).get("/echo?n=x")
    assert res.status_code == 422
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"
