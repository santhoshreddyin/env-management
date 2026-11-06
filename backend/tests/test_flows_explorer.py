def test_pairs_and_downstream_filter(seeded):
    pairs = seeded.get("/api/pairs").json()
    assert {(p["upstream_id"], p["downstream_id"]) for p in pairs} >= {("BROKER", "POLISY"), ("WEB", "BILLING")}

    broker = seeded.get("/api/pairs", params={"upstream": "Broker Portal"}).json()
    assert [p["downstream_name"] for p in broker] == ["Polisy"]
    assert broker[0]["integration_count"] == 2
    assert broker[0]["journeys"] == ["acquisition", "renewal"]

    renewal_only = seeded.get("/api/pairs", params={"journey": "renewal"}).json()
    assert {p["upstream_id"] for p in renewal_only} == {"BROKER", "POLISY"}


def test_integrations_by_names_ids_and_filters(seeded):
    both = seeded.get("/api/integrations", params={"from": "broker portal", "to": "POLISY"}).json()
    assert [i["id"] for i in both] == ["INT-001", "INT-002"]

    renewal = seeded.get("/api/integrations", params={"from": "Broker Portal", "to": "Polisy",
                                                       "journey": "Renewal"}).json()
    assert [i["id"] for i in renewal] == ["INT-002"]

    integ = renewal[0]
    assert [h["sequence"] for h in integ["hops"]] == list(range(1, 7))
    assert integ["hops"][2]["queue_name"] == "POLICY.RENEWAL.REQ"
    assert integ["hops"][0]["from_name"] == "Broker Portal"
    assert integ["narrative"][0].startswith("Broker renewal submission is an async integration")
    assert "puts the request message on queue POLICY.RENEWAL.REQ (queue manager QM_HUB01)" in integ["narrative"][3]
    assert integ["narrative"][-1].startswith("In total the flow has 6 hops (4 request, 2 reply)")

    soap = seeded.get("/api/integrations", params={"protocol": "soap"}).json()
    assert {i["id"] for i in soap} == {"INT-001", "INT-005"}
    sync = seeded.get("/api/integrations", params={"pattern": "sync", "from": "BROKER"}).json()
    assert [i["id"] for i in sync] == ["INT-001"]

    assert seeded.get("/api/integrations", params={"from": "Nope"}).status_code == 404
    assert seeded.get("/api/integrations/INT-003").json()["upstream_name"] == "Polisy"


def test_graph(seeded):
    g = seeded.get("/api/graph").json()
    assert len(g["nodes"]) == 14
    layers = {n["id"]: n["display_layer"] for n in g["nodes"]}
    assert layers["BROKER"] == "channels" and layers["DP-INT"] == "integration" and layers["MQHUB"] == "messaging"
    edge = next(e for e in g["edges"] if e["source"] == "APIGW" and e["target"] == "ESB")
    assert set(edge["integration_ids"]) == {"INT-002", "INT-004", "INT-007"}
    assert edge["protocol"] == "REST" and edge["direction"] == "request"
    summary = next(i for i in g["integrations"] if i["id"] == "INT-003")
    assert summary["system_ids"] == ["BILLING", "MFT", "POLISY"]
    apigw = next(n for n in g["nodes"] if n["id"] == "APIGW")
    assert apigw["component_details"][0]["gateway_tier"] == "API gateway (edge)"


def test_systems_journeys_config(seeded):
    assert [s["id"] for s in seeded.get("/api/systems", params={"type": "queue_manager"}).json()] == ["MQHUB"]
    assert seeded.get("/api/systems/Polisy").json()["id"] == "POLISY"
    assert seeded.get("/api/journeys").json() == ["acquisition", "claims", "renewal", "servicing"]
    cfg = seeded.get("/api/flow-config").json()
    assert [l["id"] for l in cfg["layers"]][0] == "channels"
    assert set(cfg["protocols"]) == {"REST", "SOAP", "MQ", "FILE", "MFT"}
