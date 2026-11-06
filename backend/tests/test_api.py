def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "environment" in body


def test_environment_crud(client):
    r = client.post("/api/environments", json={"name": "dev", "description": "Development"})
    assert r.status_code == 201
    env = r.json()
    assert env["name"] == "dev" and env["variable_count"] == 0

    assert client.post("/api/environments", json={"name": "dev"}).status_code == 409
    assert [e["name"] for e in client.get("/api/environments").json()] == ["dev"]

    r = client.patch(f"/api/environments/{env['id']}", json={"description": "Dev env"})
    assert r.json()["description"] == "Dev env"

    assert client.delete(f"/api/environments/{env['id']}").status_code == 204
    assert client.get(f"/api/environments/{env['id']}").status_code == 404


def test_variable_crud_and_export(client):
    env_id = client.post("/api/environments", json={"name": "staging"}).json()["id"]
    base = f"/api/environments/{env_id}/variables"

    r = client.post(base, json={"key": "DB_HOST", "value": "localhost"})
    assert r.status_code == 201
    var = r.json()

    assert client.post(base, json={"key": "DB_HOST", "value": "x"}).status_code == 409
    assert client.post(base, json={"key": "1BAD", "value": "x"}).status_code == 422

    client.post(base, json={"key": "API_KEY", "value": 'se"cret', "is_secret": True})
    assert [v["key"] for v in client.get(base).json()] == ["API_KEY", "DB_HOST"]
    assert client.get(f"/api/environments/{env_id}").json()["variable_count"] == 2

    r = client.patch(f"{base}/{var['id']}", json={"value": "db.internal"})
    assert r.json()["value"] == "db.internal"

    # SEC-03: secrets are excluded from exports unless explicitly requested (env_manager+, audited)
    export = client.get(f"{base}/export/dotenv").text
    assert export == '# API_KEY is secret and was excluded\nDB_HOST="db.internal"\n'
    export = client.get(f"{base}/export/dotenv?include_secrets=true").text
    assert export == 'API_KEY="se\\"cret"\nDB_HOST="db.internal"\n'

    assert client.delete(f"{base}/{var['id']}").status_code == 204
    assert client.delete(f"{base}/{var['id']}").status_code == 404
