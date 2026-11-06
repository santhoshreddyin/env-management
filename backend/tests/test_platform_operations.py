"""Topology, deployments, bookings, configuration, health, issues, test data, reports, integrations."""

from datetime import datetime, timedelta, timezone

import pytest

from app.auth import User
from app.platform import notify
from app.platform.sample import seed_platform


@pytest.fixture()
def demo(seeded, session_factory):
    with session_factory() as db:
        seed_platform(db, User("seed"))
        db.commit()
    return seeded


def eid(c, name):
    return next(e["id"] for e in c.get("/api/environments").json() if e["name"] == name)


def iso(days=0, hours=0):
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).isoformat()


# --- Topology (TOP-*) -------------------------------------------------------------------


def test_instances_and_integrations_per_environment(demo):
    sit2 = eid(demo, "SIT2")
    insts = demo.get(f"/api/environments/{sit2}/instances").json()
    shared = [i for i in insts if i["shared_in"]]
    assert [i["system_id"] for i in shared] == ["MQHUB"] and shared[0]["environment"] == "SIT1"
    docs = next(i for i in insts if i["system_id"] == "DOCS")
    assert docs["mode"] == "stubbed" and docs["virtualisation_ref"]
    ints = demo.get(f"/api/environments/{sit2}/integrations").json()
    assert any(i["status"] == "broken" for i in ints) and all(i["hop_count"] > 0 for i in ints if i["in_catalogue"])
    r = demo.post(f"/api/environments/{sit2}/instances", json={"system_id": "NOPE"})
    assert r.status_code == 422 and "catalogue" in r.json()["detail"]
    r = demo.post(f"/api/environments/{sit2}/instances", json={"system_id": "WEB", "instance_name": "WEB-SIT2"})
    assert r.status_code == 409


def test_verify_and_staleness(demo):
    perf = eid(demo, "PERF1")
    inst = demo.get(f"/api/environments/{perf}/instances").json()[0]
    assert inst["stale"] is True
    v = demo.post(f"/api/instances/{inst['id']}/verify").json()
    assert v["stale"] is False and v["verified_by"] == "dev-user"


def test_compare_shared_journeys_impact(demo):
    sit1, uat1 = eid(demo, "SIT1"), eid(demo, "UAT1")
    cmp = demo.get(f"/api/topology/compare?left={sit1}&right={uat1}").json()
    billing = next(s for s in cmp["systems"] if s["system_id"] == "BILLING")
    assert billing["differences"] == ["version"] and billing["left"]["version"] == "2.4.1"
    shared = demo.get("/api/topology/shared").json()
    assert shared[0]["environments"] == ["SIT1", "SIT2"]
    journeys = demo.get(f"/api/environments/{eid(demo, 'SIT2')}/journeys").json()
    assert {j["journey"] for j in journeys} >= {"acquisition", "renewal"}
    imp = demo.get("/api/impact?system_id=MQHUB").json()
    assert {e["name"] for e in imp["environments"]} >= {"SIT1", "SIT2"}
    assert "Claims Modernisation R3" in imp["projects"] and imp["integrations"]


def test_populate_and_topology_import_export(demo):
    e = demo.post("/api/environments", json={"name": "NEWENV"}).json()
    r = demo.post(f"/api/environments/{e['id']}/topology/populate").json()
    assert r["instances_added"] == 14 and r["integrations_added"] == 8
    exp = demo.get(f"/api/environments/{e['id']}/topology/export?format=json").json()
    assert len(exp["instances"]) == 14
    assert demo.get(f"/api/environments/{e['id']}/topology/export?format=mermaid").text.startswith("flowchart LR")
    xlsx = demo.get(f"/api/environments/{e['id']}/topology/export?format=xlsx").content
    target = demo.post("/api/environments", json={"name": "COPY"}).json()
    r = demo.post(f"/api/environments/{target['id']}/topology/import?dry_run=true",
                  files={"file": ("t.xlsx", xlsx, "application/octet-stream")}).json()
    assert r["valid"] is True and r["counts"] == {"instances": 14, "integrations": 8}
    bad = {"instances": [{"system_id": "WEB", "instance_name": "W1", "mode": "weird"}, {"system_id": "ZZZ"}]}
    import json as _j

    r = demo.post(f"/api/environments/{target['id']}/topology/import?dry_run=true",
                  files={"file": ("t.json", _j.dumps(bad), "application/json")}).json()
    assert {(i["row"], i["column"]) for i in r["issues"]} == {(2, "mode"), (3, "system_id")}
    good = {"instances": [{"system_id": "WEB", "instance_name": "W1", "deployed_version": "1.0"},
                          {"system_id": "BILLING", "instance_name": "B1"}],
            "integrations": [{"name": "web-to-billing", "from_instance": "W1", "to_instance": "B1", "protocol": "REST"}]}
    r = demo.post(f"/api/environments/{target['id']}/topology/import?dry_run=false",
                  files={"file": ("t.json", _j.dumps(good), "application/json")}).json()
    assert r["valid"] and r["bulk_operation_id"]
    assert len(demo.get(f"/api/environments/{target['id']}/integrations").json()) == 1


def test_catalogue_profile(demo):
    assert demo.put("/api/catalogue/systems/BILLING", json={"category": "database"}).status_code == 200
    s = next(s for s in demo.get("/api/catalogue/systems").json() if s["id"] == "BILLING")
    assert s["category"] == "database" and "SIT1" in s["environments"]
    assert demo.put("/api/catalogue/systems/BILLING", json={"category": "spaceship"}).status_code == 422


def test_catalogue_edit_does_not_wipe_topology(demo):
    """Flow catalogue edits replace all systems; environment topology must survive (no FK cascade)."""
    sit1 = eid(demo, "SIT1")
    before = len(demo.get(f"/api/environments/{sit1}/instances").json())
    sys_ = demo.get("/api/systems/DOCS").json()
    payload = {k: sys_[k] for k in ("id", "name", "type", "layer", "domain", "owner", "environment", "notes")}
    payload["component_details"] = []
    payload["notes"] = "edited"
    assert demo.put("/api/systems/DOCS", json=payload).status_code == 200
    assert len(demo.get(f"/api/environments/{sit1}/instances").json()) == before


# --- Deployments (DEP-*) ----------------------------------------------------------------


def test_record_deployment_updates_version_and_history(demo):
    r = demo.post("/api/deployments", json={"environment": "SIT1", "system": "Billing", "version": "2.6.0",
                                           "build": "b42", "pipeline": "billing-ci"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["system_id"] == "BILLING" and d["environment"] == "SIT1"
    inst = next(i for i in demo.get(f"/api/environments/{eid(demo, 'SIT1')}/instances").json()
                if i["system_id"] == "BILLING")
    assert inst["deployed_version"] == "2.6.0"
    hist = demo.get(f"/api/deployments?instance_id={inst['id']}").json()
    assert hist[0]["version"] == "2.6.0" and len(hist) >= 3
    rb = demo.post(f"/api/deployments/{d['id']}/rollback").json()
    assert rb["version"] == "2.4.1" and rb["rollback_of_id"] == d["id"]


def test_ci_ingestion_with_token_and_freeze_enforcement(demo, monkeypatch):
    from app.config import settings

    tok = demo.post("/api/admin/tokens", json={"name": "gha", "role": "contributor"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = demo.post("/api/v1/ci/deployments", headers=h, json={
        "environment": "UAT1", "system": "CLAIMS", "version": "2.4.0", "tool": "github_actions",
        "commit_sha": "abc123", "pipeline_run_url": "https://ci/run/1"})
    assert r.status_code == 201 and r.json()["source"] == "ci"
    # DEP-07 enforced freeze blocks manual deployments by contributors
    monkeypatch.setattr(settings, "dev_roles", ["contributor"])
    freeze_at = iso(days=7)
    r = demo.post("/api/deployments", json={"environment": "PreProd", "system": "CLAIMS", "version": "9",
                                           "deployed_at": freeze_at})
    assert r.status_code == 409 and "freeze" in r.json()["detail"].lower()
    r = demo.post("/api/deployments", json={"environment": "PreProd", "system": "CLAIMS", "version": "9",
                                           "deployed_at": freeze_at, "override_reason": "P1 fix"})
    assert r.status_code == 201 and r.json()["warnings"]


def test_version_matrix_and_drift(demo):
    m = demo.get("/api/version-matrix?differences_only=true").json()
    assert [e["name"] for e in m["environments"]][:2] == ["DEV1", "SIT1"]
    billing = next(r for r in m["rows"] if r["system_id"] == "BILLING")
    assert billing["distinct_versions"] >= 4
    d = demo.get(f"/api/drift?environment_id={eid(demo, 'SIT1')}").json()  # baseline from promotion path → UAT1
    assert d["baseline"]["name"] == "UAT1" and d["versions"]
    assert any(c["key"] == "LOG_LEVEL" and c["kind"] == "value" for c in d["config"])


def test_promotion_paths(demo):
    p = demo.get("/api/promotion-paths").json()[0]
    assert [s["environment"] for s in p["stages"]] == ["DEV1", "SIT1", "UAT1", "PreProd"]
    assert any(x["from"] == "SIT1" and x["to"] == "UAT1" for x in p["pending_promotions"])


# --- Bookings (BKG-*) -------------------------------------------------------------------


def test_booking_conflicts_partial_and_shared(demo):
    sit1, sit2 = eid(demo, "SIT1"), eid(demo, "SIT2")
    # whole-environment conflict with the active Digital Onboarding booking
    r = demo.post("/api/bookings", json={"environment_id": sit1, "project": "X", "start_at": iso(1), "end_at": iso(2)})
    assert r.status_code == 409 and r.json()["detail"]["conflicts"][0]["type"] == "environment"
    # booking a shared component in SIT1 conflicts with SIT2's active whole-environment booking
    mq = next(i for i in demo.get(f"/api/environments/{sit1}/instances").json() if i["system_id"] == "MQHUB")
    chk = demo.post("/api/bookings/check", json={"environment_id": sit1, "instance_ids": [mq["id"]],
                                                "start_at": iso(30), "end_at": iso(31)}).json()
    assert chk["conflicts"] == []
    chk = demo.post("/api/bookings/check", json={"environment_id": sit1, "instance_ids": [mq["id"]],
                                                "start_at": iso(5), "end_at": iso(6)}).json()
    assert {c["type"] for c in chk["conflicts"]} == {"shared_component"}
    shared = next(c for c in chk["conflicts"] if c["type"] == "shared_component")
    assert shared["environment"] == "SIT2" and shared["shared_components"] == ["MQHUB-SIT1"]
    # two partial bookings on different components of the same environment do not conflict
    insts = demo.get(f"/api/environments/{sit2}/instances").json()
    a = next(i for i in insts if i["system_id"] == "WEB")["id"]
    b = next(i for i in insts if i["system_id"] == "CRM")["id"]
    r1 = demo.post("/api/bookings", json={"environment_id": sit2, "instance_ids": [a], "project": "P1",
                                         "start_at": iso(20), "end_at": iso(22)})
    r2 = demo.post("/api/bookings", json={"environment_id": sit2, "instance_ids": [b], "project": "P2",
                                         "start_at": iso(20), "end_at": iso(22)})
    assert r1.status_code == r2.status_code == 201
    r3 = demo.post("/api/bookings", json={"environment_id": sit2, "instance_ids": [a], "project": "P3",
                                         "start_at": iso(21), "end_at": iso(23)})
    assert r3.status_code == 409 and r3.json()["detail"]["conflicts"][0]["type"] == "component"


def test_booking_approval_waitlist_and_release(demo, session_factory):
    uat = eid(demo, "UAT1")
    r = demo.post("/api/bookings", json={"environment_id": uat, "project": "Q1 cycle", "start_at": iso(40),
                                        "end_at": iso(45), "approver": "lead"}).json()
    b = r["bookings"][0]
    assert b["status"] == "Requested" and r["known_issues"]  # UAT needs approval; known issues shown (CHG-03)
    w = demo.post("/api/bookings", json={"environment_id": uat, "project": "Late", "start_at": iso(41),
                                        "end_at": iso(43), "waitlist": True}).json()["bookings"][0]
    assert w["status"] == "Waitlisted"
    pending = demo.get("/api/approvals/bookings").json()
    assert {p["project"] for p in pending} >= {"Q1 cycle", "Renewals uplift"}
    ok = demo.post(f"/api/bookings/{b['id']}/decision", json={"decision": "approve", "note": "ok"}).json()[0]
    assert ok["status"] == "Approved" and ok["decided_by"] == "dev-user"
    demo.post(f"/api/bookings/{b['id']}/decision", json={"decision": "cancel"})
    promoted = demo.get(f"/api/bookings/{w['id']}").json()
    assert promoted["status"] == "Requested"
    # BKG-05 automatic release at end date
    from app.models import Booking

    with session_factory() as db:
        x = db.get(Booking, promoted["id"])
        x.status, x.start_at, x.end_at = "Approved", datetime.now(timezone.utc) - timedelta(days=3), \
            datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    assert demo.get(f"/api/bookings/{promoted['id']}").json()["status"] in ("Approved",)
    demo.get("/api/bookings")
    assert demo.get(f"/api/bookings/{promoted['id']}").json()["status"] == "Completed"


def test_recurring_bookings_policy_and_notifications(demo):
    dev = eid(demo, "DEV1")
    r = demo.post("/api/bookings", json={"environment_id": dev, "project": "Nightly", "start_at": iso(2),
                                        "end_at": iso(3), "recurrence": {"every_days": 7, "count": 3}}).json()
    assert len(r["bookings"]) == 3 and len({b["series_id"] for b in r["bookings"]}) == 1
    assert all(b["status"] == "Approved" for b in r["bookings"])
    r = demo.post("/api/bookings", json={"environment_id": dev, "project": "Long", "start_at": iso(100),
                                        "end_at": iso(200)})
    assert r.status_code == 201 and r.json()["warnings"]  # managers may exceed the limit, with a warning
    perf = eid(demo, "PERF1")
    r = demo.post("/api/bookings", json={"environment_id": perf, "project": "x", "start_at": iso(1), "end_at": iso(2)})
    assert r.status_code == 409 and "Under maintenance" in r.json()["detail"]
    demo.post("/api/subscriptions", json={"events": ["booking.*"]})
    demo.post("/api/bookings", json={"environment_id": dev, "project": "Sub test", "start_at": iso(60), "end_at": iso(61)})
    notes = demo.get("/api/notifications").json()
    assert any("Sub test" in n["title"] for n in notes)
    assert demo.get("/api/me/access").json()["unread_notifications"] >= 1


def test_calendar_and_ics(demo):
    cal = demo.get(f"/api/calendar?start={iso(-60)}&end={iso(30)}".replace("+", "%2B")).json()
    kinds = {c["kind"] for c in cal}
    assert {"freeze", "booking", "deployment", "incident", "release"} <= kinds
    r = demo.post("/api/calendar/events", json={"environment_id": eid(demo, "SIT2"), "kind": "outage",
                                               "title": "Network", "start_at": iso(1), "end_at": iso(2)}).json()
    assert r["affected_bookings"][0]["project"] == "Claims Modernisation R3"
    ics = demo.get("/api/calendar.ics").text
    assert ics.startswith("BEGIN:VCALENDAR") and "Quarter-end change freeze" in ics


# --- Configuration (CFG-*, SEC-*) -------------------------------------------------------


def test_secrets_masked_revealed_and_audited(demo):
    sit1 = eid(demo, "SIT1")
    r = demo.post(f"/api/environments/{sit1}/variables", json={"key": "API_TOKEN", "value": "s3cr3t", "is_secret": True})
    v = r.json()
    assert v["value"] == "••••••••" and v["masked"]
    listed = next(x for x in demo.get(f"/api/environments/{sit1}/variables").json() if x["key"] == "API_TOKEN")
    assert listed["value"] == "••••••••"
    assert demo.post(f"/api/variables/{v['id']}/reveal").json()["value"] == "s3cr3t"
    assert demo.get("/api/audit/search?action=secret_reveal").json()[0]["details"]["key"] == "API_TOKEN"
    # vault reference replaces the stored value (SEC-01)
    p = demo.patch(f"/api/variables/{v['id']}", json={"vault_ref": "kv://x/api-token"}).json()
    assert demo.post(f"/api/variables/{v['id']}/reveal").json() == {"id": v["id"], "key": "API_TOKEN", "value": "",
                                                                    "vault_ref": "kv://x/api-token"}
    assert p["row_version"] == 2
    # SEC-05 credential-looking value in a plain field
    w = demo.post(f"/api/environments/{sit1}/variables", json={"key": "DB_PASS", "value": "hunter2"}).json()
    assert w["warnings"]


def test_inheritance_compare_history_restore(demo):
    sit1, uat1 = eid(demo, "SIT1"), eid(demo, "UAT1")
    cfg = {c["key"]: c for c in demo.get(f"/api/environments/{sit1}/config").json()}
    assert cfg["LOG_LEVEL"]["source"] == "environment" and cfg["LOG_LEVEL"]["overrides"] == ["global"]
    assert cfg["HTTP_TIMEOUT_MS"]["source"] == "global"
    inst = demo.get(f"/api/environments/{sit1}/instances").json()[0]
    demo.post(f"/api/instances/{inst['id']}/variables", json={"key": "LOG_LEVEL", "value": "TRACE"})
    cfg = {c["key"]: c for c in demo.get(f"/api/environments/{sit1}/config?instance_id={inst['id']}").json()}
    assert cfg["LOG_LEVEL"]["value"] == "TRACE" and cfg["LOG_LEVEL"]["overrides"] == ["global", "environment"]
    cmp = demo.get(f"/api/config/compare?env_ids={sit1},{uat1}").json()
    row = next(r for r in cmp["rows"] if r["key"] == "LOG_LEVEL")
    assert row["differs"] and row["cells"][str(uat1)]["scope"] == "global"
    pw = next(r for r in cmp["rows"] if r["key"] == "DB_PASSWORD")
    assert pw["cells"][str(sit1)]["value"] == "••••••••"
    var = next(v for v in demo.get(f"/api/environments/{sit1}/variables").json() if v["key"] == "DB_HOST")
    demo.patch(f"/api/environments/{sit1}/variables/{var['id']}", json={"value": "new-host"})
    hist = demo.get(f"/api/variables/{var['id']}/history").json()
    assert hist[0]["old_value"] == "db-sit1.example.internal" and hist[0]["new_value"] == "new-host"
    demo.post(f"/api/variables/history/{hist[0]['id']}/restore")
    assert next(v for v in demo.get(f"/api/environments/{sit1}/variables").json()
                if v["key"] == "DB_HOST")["value"] == "db-sit1.example.internal"
    demo.delete(f"/api/environments/{sit1}/variables/{var['id']}")
    h = demo.get(f"/api/variables/{var['id']}/history").json()
    demo.post(f"/api/variables/history/{h[0]['id']}/restore")
    assert any(v["key"] == "DB_HOST" for v in demo.get(f"/api/environments/{sit1}/variables").json())


def test_import_formats_preview_and_rollback(demo):
    dev = eid(demo, "DEV1")
    body = 'DB_HOST="changed"\nNEW_KEY=1\n# comment\nexport OTHER="a b"\n'
    p = demo.post(f"/api/environments/{dev}/variables/import?dry_run=true",
                  files={"file": ("x.env", body, "text/plain")}).json()
    assert p["counts"] == {"create": 2, "update": 1, "delete": 0, "unchanged": 0}
    a = demo.post(f"/api/environments/{dev}/variables/import?dry_run=false",
                  files={"file": ("x.env", body, "text/plain")}).json()
    keys = {v["key"]: v["value"] for v in demo.get(f"/api/environments/{dev}/variables").json()}
    assert keys["DB_HOST"] == "changed" and keys["OTHER"] == "a b"
    demo.post(f"/api/bulk-operations/{a['bulk_operation_id']}/rollback")
    keys = {v["key"]: v["value"] for v in demo.get(f"/api/environments/{dev}/variables").json()}
    assert keys["DB_HOST"] == "db-dev1.example.internal" and "NEW_KEY" not in keys
    y = demo.post(f"/api/environments/{dev}/variables/import?dry_run=true",
                  files={"file": ("x.yaml", "A_B: 1\nbad key: 2\n", "text/yaml")}).json()
    assert y["valid"] is False and "Invalid key" in y["issues"][0]["message"]
    for fmt in ("json", "yaml", "csv", "env"):
        r = demo.get(f"/api/environments/{dev}/variables/export?format={fmt}")
        assert r.status_code == 200 and "DB_HOST" in r.text
    assert "vault:kv://" in demo.get(f"/api/environments/{dev}/variables/export?format=json").text


def test_copy_into_protected_needs_approval(demo, monkeypatch):
    from app.config import settings

    uat, pre = eid(demo, "UAT1"), eid(demo, "PreProd")
    monkeypatch.setattr(settings, "dev_roles", ["contributor"])
    r = demo.post("/api/variables/copy", json={"source_environment_id": uat, "target_environment_id": pre,
                                              "keys": ["DB_HOST"], "overwrite": True}).json()
    assert r["status"] == "pending"
    monkeypatch.setattr(settings, "dev_roles", ["viewer", "maintainer"])
    monkeypatch.setattr(settings, "dev_user", "boss")
    res = demo.post(f"/api/approvals/{r['approval_id']}/decision", json={"decision": "approve"}).json()
    assert res["status"] == "approved"
    keys = {v["key"]: v["value"] for v in demo.get(f"/api/environments/{pre}/variables").json()}
    assert keys["DB_HOST"] == "db-uat1.example.internal"


def test_templates_and_pipeline_config(demo):
    uat = eid(demo, "UAT1")
    chk = demo.get(f"/api/environments/{uat}/config/check").json()
    assert [m["key"] for m in chk["missing"]] == ["AUDIT_SINK_URL"] and not chk["complete"]
    demo.post(f"/api/environments/{uat}/config/apply-template")
    assert any(e["key"] == "AUDIT_SINK_URL" for e in demo.get(f"/api/environments/{uat}/config/check").json()["empty"])
    tok = demo.post("/api/admin/tokens", json={"name": "pipe", "role": "viewer"}).json()["token"]
    r = demo.get("/api/v1/config/UAT1?format=env", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and 'DB_PASSWORD="vault:kv://envmgmt-uat1/db-password"' in r.text
    assert 'HTTP_TIMEOUT_MS="30000"' in r.text


# --- Health, issues, test data (HLT-*, CHG-*, TDM-*) ------------------------------------


def test_health_override_ingest_and_metrics(demo):
    sit1 = eid(demo, "SIT1")
    r = demo.post(f"/api/environments/{sit1}/health/override", json={"status": "Down", "reason": "Planned outage",
                                                                     "until": iso(hours=2)}).json()
    assert r["health_status"] == "Down" and r["health_override"]["reason"] == "Planned outage"
    demo.delete(f"/api/environments/{sit1}/health/override")
    demo.post("/api/health/events", json=[{"environment": "SIT1", "instance": "BILLING", "status": "Down",
                                           "source": "dynatrace", "message": "5xx"}])
    st = next(e for e in demo.get("/api/health/status").json() if e["name"] == "SIT1")
    assert st["health_status"] == "Degraded"
    assert any(i["health_status"] == "Down" for i in st["instances"])
    demo.post("/api/health/alertmanager", json={"alerts": [{"status": "resolved", "labels": {
        "environment": "SIT1", "system": "BILLING"}}]})
    assert next(e for e in demo.get("/api/health/status").json() if e["name"] == "SIT1")["health_status"] == "Healthy"
    m = demo.get(f"/api/environments/{eid(demo, 'SIT2')}/health/metrics").json()
    assert m["outage_count"] == 1 and m["mttr_hours"] == 5.0 and 98 < m["uptime_pct"] < 100
    hist = demo.get(f"/api/environments/{sit1}/health/history").json()
    assert hist[0]["source"] in ("rollup", "monitor:prometheus")


def test_health_check_probe(demo, monkeypatch):
    from app.platform import services

    monkeypatch.setattr(services, "probe", lambda url: ("Healthy", 12.0, "HTTP 200"))
    dev = eid(demo, "DEV1")
    demo.patch(f"/api/environments/{dev}", json={"health_check_url": "https://dev1/health"})
    r = demo.post(f"/api/environments/{dev}/health/check").json()
    assert r["results"][0]["status"] == "Healthy"


def test_issues_sla_known_and_ticket_sync(demo):
    sit1 = eid(demo, "SIT1")
    i = demo.post("/api/issues", json={"environment_id": sit1, "title": "Login broken", "severity": "critical",
                                      "external_system": "jira", "external_ref": "ENV-7", "known_issue": True}).json()
    assert i["sla_due_at"] and i["status"] == "open"
    assert demo.get(f"/api/environments/{sit1}/known-issues").json()[0]["title"] == "Login broken"
    r = demo.post("/api/tickets/webhook", json={"external_system": "jira", "external_ref": "ENV-7",
                                               "status": "Done", "resolution": "Fixed"}).json()
    assert r["action"] == "updated"
    i = demo.get("/api/issues?external_ref=ENV-7").json()[0]
    assert i["status"] == "resolved" and i["resolved_at"]
    r = demo.post("/api/tickets/webhook", json={"external_system": "servicenow", "external_ref": "INC9",
                                               "environment": "UAT1", "title": "From SN", "severity": "2"}).json()
    assert r["action"] == "created"
    rep = demo.get("/api/reports/issues").json()
    assert rep["by_category"] and sum(rep["ageing"].values()) >= 3


def test_test_data_reservation_and_jobs(demo):
    sit2 = eid(demo, "SIT2")
    d = demo.post("/api/test-data", json={"environment_id": sit2, "name": "Prod copy", "production_derived": True,
                                         "masking_status": "unmasked"}).json()
    assert d["risk"] == "high"
    assert demo.get(f"/api/environments/{sit2}").json()["production_derived_data"] is True
    demo.post(f"/api/test-data/{d['id']}/reserve", json={"until": iso(3)})
    demo.post(f"/api/test-data/{d['id']}/jobs", json={"kind": "mask", "status": "succeeded"})
    d2 = next(x for x in demo.get(f"/api/test-data?environment_id={sit2}").json() if x["id"] == d["id"])
    assert d2["masking_status"] == "masked" and d2["reserved_by"] == "dev-user" and d2["jobs"][0]["kind"] == "mask"


# --- Reports and search (RPT-*) ---------------------------------------------------------


def test_dashboard_and_reports(demo):
    d = demo.get("/api/reports/dashboard").json()
    assert d["environments"] == 7 and d["by_health"]["Down"] == 1 and d["open_issues"] == 3
    assert d["active_bookings"] and d["pending_approvals"] >= 1
    u = demo.get("/api/reports/utilisation").json()
    sit1 = next(r for r in u["rows"] if r["environment"] == "SIT1")
    assert 0 < sit1["utilisation_pct"] <= 100 and sit1["idle_hours"] > 0
    t = demo.get("/api/reports/utilisation?group_by=team&start=" + iso(-60).replace("+", "%2B")).json()
    assert any(r["team"] == "Team Falcon" for r in t["rows"])
    assert demo.get("/api/reports/utilisation?format=csv").text.startswith("environment_id,environment")
    assert demo.get("/api/reports/contention").json()["rows"]
    f = demo.get("/api/reports/forecast?weeks=4").json()
    assert {r["env_type"] for r in f["rows"]} >= {"SIT", "UAT"}
    r = demo.get(f"/api/reports/readiness/{eid(demo, 'SIT2')}?baseline_id={eid(demo, 'UAT1')}").json()
    assert r["overall"] in ("red", "amber") and {c["area"] for c in r["checks"]} >= {"Health", "Issues", "Versions"}
    c = demo.get("/api/reports/cost?group_by=programme").json()
    assert c["rows"][0]["monthly_cost"] > 0
    assert demo.get("/api/reports/cost?group_by=project&start=" + iso(-60).replace("+", "%2B")).json()["rows"]
    dq = demo.get("/api/reports/data-quality").json()
    kinds = dq["summary"]["by_kind"]
    assert kinds["stale_instance"] >= 1 and kinds["rotation_overdue"] >= 1 and kinds["missing_owner"] == 1
    assert demo.get("/api/reports/data-quality?format=xlsx").content[:2] == b"PK"
    ti = demo.get("/api/reports/test-impact").json()
    assert ti["total_hours_lost"] > 0


def test_global_search(demo):
    r = demo.get("/api/search?q=billing").json()["results"]
    assert r["systems"] and r["instances"] and r["issues"]
    r = demo.get("/api/search?q=claims").json()["results"]
    assert r["bookings"] and r["environments"]
    assert demo.get("/api/search?q=db-password").json()["results"]["variables"] == []  # vault refs not searched


# --- Integrations (INT-*) ---------------------------------------------------------------


def test_cmdb_export_and_sync(demo):
    exp = demo.get("/api/cmdb/export").json()
    assert exp["items"][0]["ci_class"] == "environment"
    items = [{"sys_id": "abc", "name": "SIT1", "owned_by": {"display_value": "New Owner"}},
             {"sys_id": "def", "name": "DR1", "u_environment_type": "Sandbox"}]
    plan = demo.post("/api/cmdb/sync", json={"items": items}).json()
    assert [p["action"] for p in plan["plan"]] == ["update", "create"]
    demo.post("/api/cmdb/sync", json={"items": items, "dry_run": False})
    envs = {e["name"]: e for e in demo.get("/api/environments").json()}
    assert envs["SIT1"]["owner"] == "New Owner" and envs["SIT1"]["cmdb_id"] == "abc" and envs["DR1"]["env_type"] == "Sandbox"


def test_discovery(demo):
    r = demo.post("/api/discovery/ingest", json={"source": "kubernetes", "environment": "SIT1", "resources": [
        {"name": "billing", "labels": {"app": "BILLING"}, "version": "9.9"}, {"name": "mystery-svc"}]}).json()
    assert r["verified"] == ["BILLING-SIT1"] and r["version_mismatches"][0]["discovered"] == "9.9"
    assert r["unknown_resources"][0]["name"] == "mystery-svc" and "WEB-SIT1" in r["recorded_but_not_found"]


def test_chatops(demo):
    r = demo.post("/api/chatops/command", data={"text": "status PERF1"}).json()
    assert "Down" in r["text"]
    r = demo.post("/api/chatops/command", json={"text": "who SIT2"}).json()
    assert "Claims Modernisation R3" in r["text"]
    day = (datetime.now(timezone.utc) + timedelta(days=50)).date().isoformat()
    r = demo.post("/api/chatops/command", data={"text": f"book DEV1 {day} {day} Chat project"}).json()
    assert "Approved" in r["text"]
    assert "Commands" in demo.post("/api/chatops/command", data={"text": "help"}).json()["text"]


def test_webhooks_delivered_after_commit(demo, monkeypatch):
    from app.config import settings

    sent = []
    monkeypatch.setattr(settings, "webhooks_enabled", True)
    monkeypatch.setitem(notify.transport, "webhook", lambda target, msg: sent.append((target, msg)) or "200")
    demo.post("/api/admin/webhooks", json={"name": "slack", "url": "https://hooks.slack.test/x", "kind": "slack",
                                           "events": ["environment.*"]})
    demo.post("/api/environments", json={"name": "HOOKED"})
    notify.drain()
    assert sent and sent[0][1]["event"] == "environment.created" and sent[0][0]["kind"] == "slack"
    assert notify.webhook_body("slack", sent[0][1]) == {"text": "Environment HOOKED created"}
