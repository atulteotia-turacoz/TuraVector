def test_overview_requires_superuser(client, login_as):
    assert client.get("/api/superadmin/overview", headers=login_as("teacher1")).status_code == 403


def test_overview(client, login_as):
    r = client.get("/api/superadmin/overview", headers=login_as("admin"))
    assert r.status_code == 200
    d = r.json()
    assert d["users"]["total"] > 0 and d["documents"]["total"] > 0
    assert len(d["logins"]["series"]) == 14
    assert {"database", "pdftron_version", "media_exists"} <= set(d["health"])
