"""Environment inventory, lifecycle, bulk operations, governance (ENV-*, GOV-*, NFR-09, INT-01)."""

import json

import pytest

from app.auth import User
from app.platform.sample import seed_platform


@pytest.fixture()
def demo(seeded, session_factory):
    with session_factory() as db:
        seed_platform(db, User("seed"))
        db.commit()
    return seeded


def env_id(client, name):
    return next(e["id"] for e in client.get("/api/environments?include_deleted=true").json() if e["name"] == name)


def test_create_with_classification_and_validation(client):
    r = client.post("/api/environments", json={"name": "SIT9", "env_type": "SIT", "owner": "Ann", "tier": "Tier 2",
                                               "programme": "Payments", "region": "UK South",
                                               "urls": [{"label": "UI", "url": "https://sit9"}], "tags": ["core"]})
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["status"] == "Available" and e["env_type"] == "SIT" and e["urls"][0]["url"] == "https://sit9"
    assert e["row_version"] == 1 and "In use" in e["allowed_transitions"]
    # ENV-01 invalid type, error names the field and the fix (NFR-06)
    r = client.post("/api/environments", json={"name": "X1", "env_type": "QA"})
    assert r.status_code == 422 and r.json()["detail"]["message"].startswith("env_type:")
    # ENV-06 mandatory fields per type
    r = client.post("/api/environments", json={"name": "UATX", "env_type": "UAT", "owner": "Ann"})
    assert r.status_code == 422
    assert any(e.startswith("delivery_manager:") for e in r.json()["detail"]["errors"])


def test_custom_attributes_rules(client):
    client.put("/api/admin/settings/custom_attributes", json=[
        {"key": "data_class", "label": "Data class", "type": "select", "options": ["A", "B"], "required_for": ["SIT"]}])
    r = client.post("/api/environments", json={"name": "S1", "env_type": "SIT"})
    assert r.status_code == 422 and "attributes.data_class" in r.json()["detail"]["message"]
    r = client.post("/api/environments", json={"name": "S1", "env_type": "SIT", "attributes": {"data_class": "Z"}})
    assert r.status_code == 422
    assert client.post("/api/environments", json={"name": "S1", "env_type": "SIT",
                                                  "attributes": {"data_class": "A"}}).status_code == 201


def test_lifecycle_transitions_and_decommission(client):
    e = client.post("/api/environments", json={"name": "E1"}).json()
    r = client.post(f"/api/environments/{e['id']}/transition", json={"to": "Retired"})
    assert r.status_code == 409 and "Allowed" in r.json()["detail"]
    e = client.post(f"/api/environments/{e['id']}/transition", json={"to": "Decommissioning", "reason": "EOL"}).json()
    assert e["status"] == "Decommissioning" and len(e["decommission_checklist"]) >= 3
    r = client.post(f"/api/environments/{e['id']}/transition", json={"to": "Retired"})
    assert r.status_code == 409 and "checklist" in r.json()["detail"]
    items = [{"item": i["item"], "done": True} for i in e["decommission_checklist"]]
    e = client.put(f"/api/environments/{e['id']}/checklist", json={"items": items}).json()
    assert all(i["done"] and i["by"] for i in e["decommission_checklist"])
    e = client.post(f"/api/environments/{e['id']}/transition", json={"to": "Retired"}).json()
    assert e["status"] == "Retired" and e["retirement_date"]
    audit = client.get("/api/audit/search?action=environment_transition").json()
    assert [a["details"]["to"] for a in audit][:2] == ["Retired", "Decommissioning"]


def test_hierarchy_cycle_rejected(client):
    a = client.post("/api/environments", json={"name": "A"}).json()
    b = client.post("/api/environments", json={"name": "B", "parent_id": a["id"]}).json()
    assert client.get(f"/api/environments/{a['id']}").json()["children"][0]["name"] == "B"
    r = client.patch(f"/api/environments/{a['id']}", json={"parent_id": b["id"]})
    assert r.status_code == 422 and "cycle" in r.json()["detail"]["message"]


def test_soft_delete_restore_and_purge(client):
    e = client.post("/api/environments", json={"name": "Temp"}).json()
    assert client.delete(f"/api/environments/{e['id']}").status_code == 204
    assert client.get(f"/api/environments/{e['id']}").status_code == 404
    assert [x["name"] for x in client.get("/api/environments?deleted_only=true").json()] == ["Temp"]
    assert client.post(f"/api/environments/{e['id']}/restore").json()["deleted_at"] is None
    client.delete(f"/api/environments/{e['id']}")
    assert client.delete(f"/api/environments/{e['id']}?purge=true").status_code == 204
    assert client.get(f"/api/environments/{e['id']}?include_deleted=true").status_code == 404


def test_optimistic_concurrency(client):
    e = client.post("/api/environments", json={"name": "C1"}).json()
    assert client.patch(f"/api/environments/{e['id']}", json={"owner": "A", "row_version": 1}).status_code == 200
    r = client.patch(f"/api/environments/{e['id']}", json={"owner": "B", "row_version": 1})
    assert r.status_code == 409 and "Reload" in r.json()["detail"]


def test_clone_copies_topology_and_non_secret_config(demo):
    sit1 = env_id(demo, "SIT1")
    r = demo.post(f"/api/environments/{sit1}/clone", json={"name": "SIT3"})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["status"] == "Provisioning" and new["env_type"] == "SIT"
    insts = demo.get(f"/api/environments/{new['id']}/instances").json()
    assert len(insts) == len([i for i in demo.get(f"/api/environments/{sit1}/instances").json() if not i["shared_in"]])
    assert all(i["deployed_version"] is None for i in insts)
    vars_ = {v["key"]: v for v in demo.get(f"/api/environments/{new['id']}/variables").json()}
    assert vars_["DB_HOST"]["value"] == "db-sit1.example.internal" and vars_["DB_PASSWORD"]["vault_ref"] is None


def test_bulk_import_preview_apply_and_rollback(client):
    client.post("/api/environments", json={"name": "DEV1", "owner": "old"})
    csv = "name,env_type,owner,tags,parent\nDEV1,DEV,new owner,a,\nSIT5,SIT,Bo,\"x,y\",DEV1\n,DEV,,,\n"
    r = client.post("/api/environments/import?dry_run=true", files={"file": ("envs.csv", csv, "text/csv")})
    body = r.json()
    assert body["valid"] is False and body["issues"][0]["row"] == 4 and body["issues"][0]["column"] == "name"
    csv = "\n".join(csv.splitlines()[:3]) + "\n"
    body = client.post("/api/environments/import?dry_run=true", files={"file": ("envs.csv", csv, "text/csv")}).json()
    assert body["valid"] and body["counts"] == {"create": 1, "update": 1, "unchanged": 0}
    assert body["plan"][0]["changes"]["owner"] == ["old", "new owner"]
    body = client.post("/api/environments/import?dry_run=false", files={"file": ("envs.csv", csv, "text/csv")}).json()
    op = body["bulk_operation_id"]
    envs = {e["name"]: e for e in client.get("/api/environments").json()}
    assert envs["DEV1"]["owner"] == "new owner" and envs["SIT5"]["tags"] == ["x", "y"]
    assert envs["SIT5"]["parent"] == "DEV1"
    r = client.post(f"/api/bulk-operations/{op}/rollback").json()
    assert r["undone"] == 2
    envs = {e["name"]: e for e in client.get("/api/environments").json()}
    assert envs["DEV1"]["owner"] == "old" and "SIT5" not in envs
    assert client.post(f"/api/bulk-operations/{op}/rollback").status_code == 409


def test_export_formats(demo):
    r = demo.get("/api/environments/export?format=csv")
    assert r.status_code == 200 and r.text.splitlines()[0].startswith("id,name,description,env_type")
    assert demo.get("/api/environments/export?format=xlsx").content[:2] == b"PK"
    assert len(json.loads(demo.get("/api/environments/export?format=json").content)) == 7


def test_bulk_update(demo):
    ids = [env_id(demo, "SIT1"), env_id(demo, "SIT2")]
    r = demo.patch("/api/environments/bulk", json={"ids": ids, "changes": {"support_group": "Team X"}})
    assert r.json()["updated"] == 2
    assert {e["support_group"] for e in demo.get("/api/environments?env_type=SIT").json()} == {"Team X"}


def test_list_filters_and_sort(demo):
    names = [e["name"] for e in demo.get("/api/environments?programme=Claims Modernisation&sort=-name").json()]
    assert names == ["UAT1", "SIT2"]
    assert [e["name"] for e in demo.get("/api/environments?health=Down").json()] == ["PERF1"]
    assert [e["name"] for e in demo.get("/api/environments?tag=regulated").json()] == ["PreProd", "UAT1"]
    sit2 = next(e for e in demo.get("/api/environments?q=sit2").json())
    assert sit2["active_bookings"][0]["project"] == "Claims Modernisation R3" and sit2["open_issues"] == 1


def test_environment_request_workflow(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "dev_roles", ["booker"])
    r = client.post("/api/environments/requests", json={"name": "NEW1", "env_type": "SIT", "justification": "R4"})
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["status"] == "Requested" and e["requested_by"] == "dev-user" and e["sla_due_at"]
    assert client.post(f"/api/environments/{e['id']}/transition", json={"to": "Provisioning"}).status_code == 403
    monkeypatch.setattr(settings, "dev_roles", ["env_manager"])
    assert client.post(f"/api/environments/{e['id']}/transition", json={"to": "Provisioning"}).json()["status"] == \
        "Provisioning"


def test_roles_and_scoped_assignments(client, monkeypatch):
    from app.config import settings

    a = client.post("/api/environments", json={"name": "PA", "programme": "Payments"}).json()
    b = client.post("/api/environments", json={"name": "CL", "programme": "Claims"}).json()
    client.post("/api/admin/roles", json={"principal": "carol", "role": "env_manager", "scope_type": "programme",
                                          "scope_value": "Payments"})
    monkeypatch.setattr(settings, "auth_mode", "header")
    h = {"X-Forwarded-User": "carol"}
    assert client.patch(f"/api/environments/{a['id']}", json={"owner": "c"}, headers=h).status_code == 200
    r = client.patch(f"/api/environments/{b['id']}", json={"owner": "c"}, headers=h)
    assert r.status_code == 403 and "env_manager role" in r.json()["detail"]
    assert client.get("/api/admin/roles", headers=h).status_code == 403
    # GOV-06 portfolio segregation: carol only sees Payments
    monkeypatch.setattr(settings, "portfolio_segregation", True)
    assert [e["name"] for e in client.get("/api/environments", headers=h).json()] == ["PA"]
    assert client.get(f"/api/environments/{b['id']}", headers=h).status_code == 404
    # group-to-role mapping (INT-05)
    monkeypatch.setattr(settings, "env_manager_groups", ["env-managers"])
    me = client.get("/api/me/access", headers={"X-Forwarded-User": "dan", "X-Forwarded-Groups": "env-managers"}).json()
    assert me["role"] == "env_manager"


def test_api_tokens_and_versioned_api(client):
    t = client.post("/api/admin/tokens", json={"name": "jenkins", "role": "contributor"}).json()
    assert t["token"].startswith("emt_")
    h = {"Authorization": f"Bearer {t['token']}"}
    assert client.get("/api/v1/environments", headers=h).status_code == 200
    assert client.post("/api/v1/environments", json={"name": "Z"}, headers=h).status_code == 403
    assert client.get("/api/v1/environments", headers={"Authorization": "Bearer emt_nope"}).status_code == 401
    client.delete(f"/api/admin/tokens/{t['id']}")
    assert client.get("/api/v1/environments", headers=h).status_code == 401


def test_audit_chain_is_tamper_evident(demo, session_factory):
    from app.flows.models import AuditLog

    demo.post("/api/environments", json={"name": "AuditMe"})
    assert demo.get("/api/audit/verify").json()["valid"] is True
    with session_factory() as db:
        row = db.query(AuditLog).order_by(AuditLog.id).first()
        row.user = "mallory"
        db.commit()
    v = demo.get("/api/audit/verify").json()
    assert v["valid"] is False and v["broken_at_id"] is not None
    assert demo.get("/api/audit/search?format=csv").text.startswith("id,at,user,action")


def test_settings_and_meta(client):
    meta = client.get("/api/environments/meta").json()
    assert "PreProd" in meta["env_types"] and meta["transitions"]["Requested"] == ["Provisioning", "Retired"]
    assert client.put("/api/admin/settings/env_types", json={"bad": 1}).status_code == 422
    client.put("/api/admin/settings/env_types", json=["DEV", "SIT", "UAT", "PreProd", "Perf", "Training", "Sandbox", "DR"])
    assert client.post("/api/environments", json={"name": "DR1", "env_type": "DR"}).status_code == 201


def test_saved_views_and_metrics(client):
    client.post("/api/views", json={"page": "environments", "name": "SIT only", "config": {"env_type": "SIT"}})
    assert client.get("/api/views?page=environments").json()[0]["config"] == {"env_type": "SIT"}
    client.get("/api/environments")
    assert "envmgmt_http_requests_total" in client.get("/api/metrics").text


def test_sample_data_endpoint(client):
    r = client.post("/api/admin/sample-data")
    assert r.status_code == 200 and r.json()["environments"] == 7
    assert client.post("/api/admin/sample-data").status_code == 409
