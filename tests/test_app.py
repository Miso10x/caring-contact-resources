import importlib

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VOLUNTEER_PASSWORD", "vol-pass")
    monkeypatch.setenv("ADMIN_PASSWORD", "staff-pass")
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("COOKIE_INSECURE", "1")
    import store
    import app as app_module
    importlib.reload(store)
    app_module = importlib.reload(app_module)
    app_module._failures.clear()
    return app_module.app.test_client()


def login(client, pw):
    return client.post("/login", data={"password": pw})


WRITE = {"X-Requested-With": "fetch"}


def test_healthz_is_public(client):
    assert client.get("/healthz").status_code == 200


def test_everything_else_needs_a_password(client):
    assert client.get("/").headers["Location"].endswith("/login")
    assert client.get("/api/data").status_code == 401
    assert client.put("/api/resources/x", json={}, headers=WRITE).status_code == 401


def test_wrong_password_is_refused(client):
    assert login(client, "nope").status_code == 401
    assert client.get("/api/data").status_code == 401


def test_lockout_after_five_wrong_tries(client):
    for _ in range(5):
        login(client, "nope")
    assert login(client, "vol-pass").status_code == 429


def test_volunteer_reads_seeded_data_but_cannot_edit(client):
    assert login(client, "vol-pass").status_code == 302
    data = client.get("/api/data").get_json()
    assert len(data["resources"]) == 134
    assert any(r["data"].get("suggestion") for r in data["resources"])
    assert client.get("/api/me").get_json()["role"] == "volunteer"
    assert client.put("/api/resources/new-one", json={"name": "x"}, headers=WRITE).status_code == 403
    assert client.delete("/api/resources/new-one", headers=WRITE).status_code == 403


def test_pes_rule_is_in_the_starting_data(client):
    login(client, "vol-pass")
    notices = {n["id"]: n["data"] for n in client.get("/api/data").get_json()["notices"]}
    assert "do not call PES" in notices["pes"]["title"]
    assert "police" in notices["pes"]["body"]


def test_staff_can_add_edit_and_delete(client):
    login(client, "staff-pass")
    assert client.get("/api/me").get_json()["role"] == "admin"
    assert client.put("/api/resources/test-line", json={"name": "Test line"}, headers=WRITE).status_code == 200
    names = {r["id"]: r["data"]["name"] for r in client.get("/api/data").get_json()["resources"]}
    assert names["test-line"] == "Test line"
    assert client.delete("/api/resources/test-line", headers=WRITE).status_code == 200
    ids = {r["id"] for r in client.get("/api/data").get_json()["resources"]}
    assert "test-line" not in ids


def test_writes_need_the_fetch_header_and_a_known_collection(client):
    login(client, "staff-pass")
    assert client.put("/api/resources/x", json={"name": "x"}).status_code == 400
    assert client.put("/api/passwords/x", json={"a": 1}, headers=WRITE).status_code == 404
    assert client.put("/api/resources/Bad Id", json={"a": 1}, headers=WRITE).status_code == 404


def test_edits_survive_a_restart_and_are_not_reseeded(client, tmp_path):
    login(client, "staff-pass")
    client.delete("/api/resources/grief-goodgrief", headers=WRITE)
    import store
    assert store.seed_if_empty() == 0
    assert "grief-goodgrief" not in {r["id"] for r in store.all_docs()["resources"]}


def test_sign_in_fails_closed_without_passwords(client, monkeypatch):
    monkeypatch.delenv("VOLUNTEER_PASSWORD")
    monkeypatch.delenv("ADMIN_PASSWORD")
    assert login(client, "").status_code == 503


def test_logout(client):
    login(client, "vol-pass")
    client.post("/logout")
    assert client.get("/api/data").status_code == 401
