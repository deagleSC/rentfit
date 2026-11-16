import uuid

from app.core.auth import verify_token
from app.core.errors import AppError
from tests.conftest import make_token


async def test_valid_hs256_token() -> None:
    uid = uuid.uuid4()
    p = await verify_token(make_token(uid, email="a@b.c"))
    assert p.user_id == uid and p.email == "a@b.c"


async def test_expired_token() -> None:
    try:
        await verify_token(make_token(uuid.uuid4(), exp_in=-10))
    except AppError as e:
        assert e.code == "token_expired"
    else:
        raise AssertionError("expected AppError")


async def test_garbage_token() -> None:
    try:
        await verify_token("not.a.token")
    except AppError as e:
        assert e.code == "invalid_token"
    else:
        raise AssertionError("expected AppError")


async def test_me_requires_auth(api) -> None:  # type: ignore[no-untyped-def]
    res = await api.get("/v1/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "unauthenticated"
