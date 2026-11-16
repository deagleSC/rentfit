"""Reference endpoints against the real database, rolled back (see conftest)."""

from tests.conftest import auth_header

SQUARE = '{"type":"MultiPolygon","coordinates":[[[[77.6,12.9],[77.7,12.9],[77.7,13.0],[77.6,13.0],[77.6,12.9]]]]}'


async def _seed(db) -> None:  # type: ignore[no-untyped-def]
    await db.as_owner()
    await db.conn.execute(
        "insert into cities (slug, name, center) values ('testcity', 'Testcity', st_point(77.65, 12.95, 4326))"
        " on conflict do nothing"
    )
    await db.conn.execute(
        "insert into localities (city, name, boundary, centroid, median_rent) values "
        "('testcity', 'Alpha', st_geomfromgeojson(%s)::geography, st_point(77.65, 12.95, 4326), '{\"2\": 25000}')",
        (SQUARE,),
    )
    await db.conn.execute(
        "insert into pois (city, name, kind, location) values "
        "('testcity', 'Alpha Metro', 'metro_station', st_point(77.66, 12.96, 4326)),"
        "('testcity', 'Alpha Hospital', 'hospital', st_point(77.64, 12.94, 4326))"
    )


async def test_reference_endpoints(db, api) -> None:  # type: ignore[no-untyped-def]
    await _seed(db)
    h = auth_header(await db.auth_user())

    cities = (await api.get("/v1/cities", headers=h)).json()["data"]
    assert {"slug": "testcity", "name": "Testcity", "center": [77.65, 12.95], "default_zoom": 11.0} in cities

    locs = (await api.get("/v1/localities?city=testcity", headers=h)).json()["data"]
    assert [loc["name"] for loc in locs] == ["Alpha"] and "boundary" not in locs[0]
    locs = (await api.get("/v1/localities?city=testcity&geometry=true", headers=h)).json()["data"]
    assert locs[0]["boundary"]["type"] == "MultiPolygon"

    pois = (await api.get("/v1/pois?city=testcity&kind=metro_station", headers=h)).json()["data"]
    assert [p["name"] for p in pois] == ["Alpha Metro"]
    pois = (await api.get("/v1/pois?city=testcity", headers=h)).json()["data"]
    assert len(pois) == 2

    res = await api.get("/v1/localities?city=atlantis", headers=h)
    assert res.status_code == 404 and res.json()["error"]["code"] == "unknown_city"


async def test_reference_requires_login(api) -> None:  # type: ignore[no-untyped-def]
    assert (await api.get("/v1/cities")).status_code == 401
