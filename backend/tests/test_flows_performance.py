"""NFR: path render under 1 s for ~300 systems and ~2,000 hops (backend share)."""

import time

from app.auth import User
from app.flows.repository import commit_dataset
from app.flows.schemas import Dataset, HopIn, IntegrationIn, SystemIn

TYPES = ["upstream", "gateway", "gateway", "queue_manager", "mainframe", "downstream"]


def large_dataset(n_systems=300, n_integrations=400, hops_per=5) -> Dataset:
    systems = [SystemIn(id=f"S{i}", name=f"System {i}", type=TYPES[i % len(TYPES)]) for i in range(n_systems)]
    integrations, hops = [], []
    for i in range(n_integrations):
        path = [f"S{(i * 7 + k * 53) % n_systems}" for k in range(hops_per + 1)]
        if len(set(path)) != len(path):
            path = [f"S{(i + k) % n_systems}" for k in range(hops_per + 1)]
        integrations.append(IntegrationIn(id=f"I{i}", name=f"Integration {i}", journey=f"j{i % 5}",
                                          upstream_id=path[0], downstream_id=path[-1], pattern="sync"))
        hops += [HopIn(integration_id=f"I{i}", sequence=k + 1, from_system=path[k], to_system=path[k + 1],
                       protocol=["REST", "SOAP", "MQ", "FILE"][k % 4], queue_name="Q" if k % 4 == 2 else None)
                 for k in range(hops_per)]
    return Dataset(systems=systems, integrations=integrations, hops=hops)


def test_large_dataset_queries_are_fast(client, session_factory):
    ds = large_dataset()
    assert len(ds.hops) == 2000
    with session_factory() as db:
        commit_dataset(db, ds, user=User("perf"), source="seed", summary="perf", audit_action="seed")

    start = time.perf_counter()
    g = client.get("/api/graph")
    graph_time = time.perf_counter() - start
    assert g.status_code == 200 and len(g.json()["nodes"]) == 300

    up, down = ds.integrations[0].upstream_id, ds.integrations[0].downstream_id
    start = time.perf_counter()
    r = client.get("/api/integrations", params={"from": up, "to": down})
    path_time = time.perf_counter() - start
    assert r.status_code == 200 and r.json()

    assert graph_time < 1.0, graph_time
    assert path_time < 0.5, path_time
