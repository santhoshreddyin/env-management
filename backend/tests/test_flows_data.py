import json

from tests.helpers import sample_workbook, upload


def test_import_sample_and_history(client):
    r = upload(client, sample_workbook(), dry_run=True)
    report = r.json()
    assert report["valid"] and not report["imported"] and report["counts"]["hops"] == 41
    assert client.get("/api/imports").json() == []

    report = upload(client, sample_workbook()).json()
    assert report["imported"] and report["version_id"] == 1 and report["error_count"] == 0
    versions = client.get("/api/imports").json()
    assert len(versions) == 1 and versions[0]["is_current"] and versions[0]["source"] == "import"
    assert versions[0]["created_by"] == "dev-user"
    audit = client.get("/api/audit").json()
    assert audit[0]["action"] == "import" and audit[0]["details"]["filename"] == "flows.xlsx"


def test_import_reports_errors_by_row_and_column(client):
    def break_it(wb):
        wb["Systems"]["C3"] = "spaceship"        # invalid type
        wb["Systems"]["A4"] = "BROKER"           # duplicate id (row 2 is BROKER)
        wb["Integrations"]["D2"] = "GHOST"       # unknown upstream
        wb["Hops"]["B3"] = 5                     # INT-001 sequence gap/duplicate
        wb["Hops"]["E4"] = "SMTP"                # invalid protocol

    report = upload(client, sample_workbook(break_it)).json()
    assert not report["valid"] and not report["imported"]
    found = {(i["sheet"], i["row"], i["column"]) for i in report["issues"] if i["severity"] == "error"}
    assert ("Systems", 3, "type") in found
    assert ("Hops", 4, "protocol") in found
    # Type errors stop before cross-checks; fix them and the reference checks run.

    def refs_only(wb):
        wb["Systems"]["A4"] = "BROKER"
        wb["Integrations"]["D2"] = "GHOST"
        wb["Hops"]["B3"] = 5

    report = upload(client, sample_workbook(refs_only)).json()
    errors = {(i["sheet"], i["row"], i["column"]): i["message"] for i in report["issues"] if i["severity"] == "error"}
    assert "Duplicate system id 'BROKER'" in errors[("Systems", 4, "id")]
    assert "Unknown system 'GHOST'" in errors[("Integrations", 2, "upstream_id")]
    assert any(k[0] == "Hops" and k[2] == "sequence" and "Broken sequence" in m for k, m in errors.items())
    audit = client.get("/api/audit").json()
    assert audit[0]["action"] == "import_rejected"


def test_import_rejects_non_excel_and_missing_sheets(client):
    report = upload(client, b"not excel").json()
    assert not report["valid"] and report["issues"][0]["sheet"] == "(workbook)"

    report = upload(client, sample_workbook(lambda wb: wb.remove(wb["Hops"]))).json()
    assert any(i["message"] == "Missing sheet 'Hops'" for i in report["issues"])


def test_warnings_do_not_block(client):
    def add_orphan(wb):
        wb["Systems"].append(["LONELY", "Lonely System", "downstream"])

    report = upload(client, sample_workbook(add_orphan)).json()
    assert report["imported"] and report["warning_count"] == 1
    assert "Orphan system 'LONELY'" in report["issues"][0]["message"]


def test_export_roundtrip(seeded):
    xlsx = seeded.get("/api/export?format=xlsx")
    assert xlsx.status_code == 200 and "attachment" in xlsx.headers["content-disposition"]
    report = upload(seeded, xlsx.content, dry_run=True).json()
    assert report["valid"] and report["counts"] == {"systems": 14, "integrations": 8, "hops": 41,
                                                    "component_details": 6}
    data = seeded.get("/api/export?format=json").json()
    assert data["version_id"] == 1 and len(data["hops"]) == 41

    template = seeded.get("/api/template")
    report = upload(seeded, template.content, dry_run=True).json()
    assert report["valid"] and report["counts"]["systems"] == 0


def test_rollback(client):
    upload(client, sample_workbook())
    upload(client, sample_workbook(lambda wb: wb["Systems"].cell(row=2, column=2, value="Broker Portal v2")))
    assert client.get("/api/systems/BROKER").json()["name"] == "Broker Portal v2"

    v = client.post("/api/imports/1/rollback").json()
    assert v["id"] == 3 and v["source"] == "rollback" and v["is_current"]
    assert client.get("/api/systems/BROKER").json()["name"] == "Broker Portal"
    assert [x["id"] for x in client.get("/api/imports").json()] == [3, 2, 1]
    assert client.get("/api/audit").json()[0]["details"]["restored_version"] == 1
    assert client.post("/api/imports/99/rollback").status_code == 404


def test_roles(seeded, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "dev_roles", ["viewer"])
    assert seeded.get("/api/graph").status_code == 200
    assert seeded.get("/api/export").status_code == 200
    assert upload(seeded, sample_workbook()).status_code == 403
    assert seeded.post("/api/imports/1/rollback").status_code == 403
    assert seeded.get("/api/audit").status_code == 403
    assert seeded.delete("/api/systems/DOCS").status_code == 403
    assert seeded.post("/api/environments", json={"name": "x"}).status_code == 403

    monkeypatch.setattr(settings, "auth_mode", "header")
    assert seeded.get("/api/graph").status_code == 401
    hdrs = {"X-Forwarded-User": "alice", "X-Forwarded-Groups": "staff,integration-maintainers"}
    me = seeded.get("/api/me", headers=hdrs).json()
    assert me == {"name": "alice", "roles": ["admin", "maintainer", "viewer"]}
    viewer = seeded.get("/api/me", headers={"X-Forwarded-User": "bob"}).json()
    assert viewer["roles"] == ["viewer"]

    monkeypatch.setattr(settings, "viewer_groups", ["architects"])
    assert seeded.get("/api/graph", headers={"X-Forwarded-User": "eve"}).status_code == 403


def test_no_payload_or_credentials_in_audit_details(seeded):
    seeded.delete("/api/integrations/INT-008")
    entry = seeded.get("/api/audit").json()[0]
    assert entry["action"] == "delete_integration" and entry["entity_id"] == "INT-008"
    assert len(json.dumps(entry["details"])) < 500
