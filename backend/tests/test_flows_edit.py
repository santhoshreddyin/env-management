def test_create_update_delete_system(seeded):
    payload = {"id": "FRAUD", "name": "Fraud Engine", "type": "downstream", "owner": "Risk IT",
               "component_details": [{"endpoint": "https://fraud.internal"}]}
    r = seeded.post("/api/systems", json=payload)
    assert r.status_code == 201
    assert "Orphan" in r.json()["warnings"][0]["message"]
    assert seeded.post("/api/systems", json=payload).status_code == 409

    payload["name"] = "Fraud Scoring"
    assert seeded.put("/api/systems/FRAUD", json=payload).status_code == 200
    sys = seeded.get("/api/systems/FRAUD").json()
    assert sys["name"] == "Fraud Scoring" and sys["component_details"][0]["endpoint"] == "https://fraud.internal"

    assert seeded.delete("/api/systems/FRAUD").status_code == 204
    assert seeded.get("/api/systems/FRAUD").status_code == 404
    versions = seeded.get("/api/imports").json()
    assert [v["source"] for v in versions[:3]] == ["edit", "edit", "edit"]


def test_edit_validation_rejects_broken_changes(seeded):
    r = seeded.delete("/api/systems/POLISY")  # still referenced by integrations
    assert r.status_code == 422
    assert "Unknown system 'POLISY'" in r.json()["detail"]["message"]

    r = seeded.post("/api/systems", json={"id": "X", "name": "polisy", "type": "downstream"})
    assert r.status_code == 422 and "Duplicate system name" in r.json()["detail"]["message"]

    assert seeded.put("/api/systems/BROKER", json={"id": "OTHER", "name": "B", "type": "upstream"}).status_code == 422


def test_create_and_update_integration_with_hops(seeded):
    payload = {
        "id": "INT-100", "name": "Web quote", "journey": "acquisition", "upstream_id": "WEB",
        "downstream_id": "POLISY", "pattern": "sync", "primary_protocol": "REST",
        "hops": [
            {"sequence": 2, "from_system": "APIGW", "to_system": "POLISY", "protocol": "REST"},
            {"sequence": 1, "from_system": "WEB", "to_system": "APIGW", "protocol": "REST"},
        ],
    }
    assert seeded.post("/api/integrations", json=payload).status_code == 201
    integ = seeded.get("/api/integrations/INT-100").json()
    assert [(h["sequence"], h["from_system"]) for h in integ["hops"]] == [(1, "WEB"), (2, "APIGW")]

    payload["hops"][0]["sequence"] = 3  # gap
    r = seeded.put("/api/integrations/INT-100", json=payload)
    assert r.status_code == 422 and "Broken sequence" in r.json()["detail"]["message"]

    payload["hops"] = []
    r = seeded.put("/api/integrations/INT-100", json=payload)
    assert r.status_code == 422 and "has no hops" in r.json()["detail"]["message"]

    assert seeded.delete("/api/integrations/INT-100").status_code == 204
    assert seeded.get("/api/integrations/INT-100").status_code == 404
