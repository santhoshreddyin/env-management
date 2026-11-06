"""NFR-01/02: list and search views stay fast at 500 environments and 5,000 system instances."""

import time

from sqlalchemy import insert

from app.models import Booking, Environment, SystemInstance


def test_scale(seeded, session_factory):
    from datetime import datetime, timedelta, timezone

    t = datetime.now(timezone.utc)
    with session_factory() as db:
        db.execute(insert(Environment), [{"name": f"ENV{i:03}", "env_type": "SIT", "status": "Available",
                                          "health_status": "Healthy", "row_version": 1, "created_at": t,
                                          "updated_at": t, "programme": f"P{i % 10}"} for i in range(500)])
        db.execute(insert(SystemInstance), [{"environment_id": 1 + i // 10, "system_id": ["WEB", "BILLING", "CLAIMS"][i % 3],
                                             "instance_name": f"I{i}", "deployed_version": f"1.{i % 7}", "mode": "real",
                                             "health_status": "Healthy", "row_version": 1, "updated_at": t}
                                            for i in range(5000)])
        db.execute(insert(Booking), [{"environment_id": 1 + i % 500, "project": f"Proj{i % 40}", "requested_by": "x",
                                      "start_at": t + timedelta(days=i % 30), "end_at": t + timedelta(days=i % 30 + 3),
                                      "status": "Approved", "priority": "project", "row_version": 1, "created_at": t,
                                      "escalated": False, "expiry_notified": False} for i in range(2000)])
        db.commit()
    for url in ("/api/environments", "/api/version-matrix", "/api/search?q=ENV4", "/api/reports/dashboard",
                "/api/environments/1/instances"):
        start = time.perf_counter()
        r = seeded.get(url)
        elapsed = time.perf_counter() - start
        assert r.status_code == 200, url
        assert elapsed < 2.0, f"{url} took {elapsed:.2f}s"
    assert len(seeded.get("/api/environments").json()) == 500
