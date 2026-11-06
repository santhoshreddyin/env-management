"""Demo inventory for first-time setup and e2e tests (RPT-10). Builds on the flow sample catalogue."""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import User
from app.flows.models import Integration, System
from app.models import (
    Booking,
    CalendarEvent,
    ConfigTemplateKey,
    DataJob,
    Deployment,
    Environment,
    EnvironmentIntegration,
    HealthResult,
    Issue,
    PromotionPath,
    SystemInstance,
    SystemProfile,
    TestDataSet,
    Variable,
)
from app.platform.common import audit, now

ENVS = [
    # name, type, tier, programme, owner, region, platform, status, health, cost
    ("DEV1", "DEV", "Tier 3", "Digital Transformation", "Priya Shah", "UK South", "Azure", "Available", "Healthy", 1800),
    ("SIT1", "SIT", "Tier 2", "Digital Transformation", "Priya Shah", "UK South", "Azure", "In use", "Healthy", 4200),
    ("SIT2", "SIT", "Tier 2", "Claims Modernisation", "Tom Reid", "UK South", "On-premises", "In use", "Degraded", 3900),
    ("UAT1", "UAT", "Tier 1", "Claims Modernisation", "Tom Reid", "UK West", "On-premises", "Available", "Healthy", 6100),
    ("PreProd", "PreProd", "Tier 1", "Enterprise Platforms", "Dana Okafor", "UK West", "On-premises", "Frozen",
     "Healthy", 9800),
    ("PERF1", "Perf", "Tier 1", "Enterprise Platforms", "Dana Okafor", "UK South", "AWS", "Under maintenance",
     "Down", 7400),
    ("TRN1", "Training", "Tier 3", "Digital Transformation", None, "UK South", "Azure", "Requested", "Unknown", 900),
]
VERSIONS = {"DEV1": "2.5.0-rc1", "SIT1": "2.4.1", "SIT2": "2.4.0", "UAT1": "2.3.2", "PreProd": "2.3.2",
            "PERF1": "2.3.1", "TRN1": None}


def seed_platform(db: Session, user: User | None = None) -> dict[str, Any]:
    user = user or User("seed")
    t = now()
    day = timedelta(days=1)
    systems = list(db.scalars(select(System).order_by(System.id)))
    integrations = list(db.scalars(select(Integration)))
    envs: dict[str, Environment] = {}
    for name, typ, tier, prog, owner, region, platform, st, health, cost in ENVS:
        e = Environment(
            name=name, env_type=typ, tier=tier, programme=prog, owner=owner, region=region, platform=platform,
            status=st, health_status=health, health_checked_at=t - timedelta(minutes=7), run_cost=cost,
            description=f"{typ} environment for {prog}", purpose=f"{typ} testing", cost_centre=f"CC-{100 + len(envs)}",
            delivery_manager="Alex Morgan" if typ in ("UAT", "PreProd") else None,
            support_group="Env Ops" if owner else None, technical_contact="env-ops@example.com",
            hosting_location="Azure sub-envmgmt-01" if platform == "Azure" else "DC North",
            network_zone="Internal", family="Core insurance" if typ != "Training" else "Training",
            urls=[{"label": "Portal", "url": f"https://{name.lower()}.example.internal"}],
            tags=["core"] + (["regulated"] if typ in ("UAT", "PreProd") else []),
            chargeback_model="per-booking" if typ in ("SIT", "UAT") else "fixed",
            updated_by=user.name,
        )
        if st == "Requested":
            e.requested_by, e.requested_at, e.sla_due_at = "jo.bloggs", t - 3 * day, t + 7 * day
        db.add(e)
        envs[name] = e
    db.flush()
    envs["SIT2"].parent_id = envs["SIT1"].id
    envs["UAT1"].sensitive_data = envs["UAT1"].production_derived_data = True
    envs["UAT1"].data_controls = "Masked nightly copy of production; access restricted to UAT testers"
    envs["PreProd"].health_override_status = None

    categories = {"gateway": "middleware", "queue_manager": "middleware", "mainframe": "mainframe"}
    for s in systems:
        db.add(SystemProfile(system_id=s.id, category=categories.get(s.type, "application"),
                             criticality="critical" if s.type in ("mainframe", "gateway") else "high",
                             technology={"mainframe": "IBM z/OS CICS", "gateway": "IBM DataPower / APIM",
                                         "queue_manager": "IBM MQ"}.get(s.type, "Java / Spring")))

    insts: dict[tuple[str, str], SystemInstance] = {}
    for env_name, e in envs.items():
        if env_name == "TRN1":
            continue
        for s in systems:
            if env_name == "SIT2" and s.id == "MQHUB":
                continue  # SIT2 shares SIT1's MQ hub (TOP-05)
            mode = "real"
            ref = None
            if env_name in ("DEV1",) and s.type == "mainframe":
                mode, ref = "virtualised", "SV-POLISY-v3 (Parasoft)"
            if env_name == "SIT2" and s.id == "DOCS":
                mode, ref = "stubbed", "wiremock/docs-stub"
            if env_name == "PERF1" and s.id == "CRM":
                mode = "not_available"
            ver = VERSIONS[env_name] if s.type in ("upstream", "downstream") else None
            i = SystemInstance(environment_id=e.id, system_id=s.id, instance_name=f"{s.id}-{env_name}",
                               url=f"https://{s.id.lower()}.{env_name.lower()}.example.internal", deployed_version=ver,
                               build=f"b{sum(map(ord, s.id + env_name)) % 900 + 100}" if ver else None, mode=mode,
                               virtualisation_ref=ref,
                               health_status="Down" if env_name == "PERF1" else ("Unknown" if mode != "real" else "Healthy"),
                               health_checked_at=t - timedelta(minutes=7),
                               last_verified=(t - timedelta(days=20 if env_name != "PERF1" else 140)).date(),
                               verified_by="Env Ops")
            db.add(i)
            insts[(env_name, s.id)] = i
    db.flush()
    if ("SIT1", "MQHUB") in insts:
        insts[("SIT1", "MQHUB")].shared_with = [envs["SIT2"]]
        insts[("SIT2", "MQHUB")] = insts[("SIT1", "MQHUB")]
    if ("SIT2", "BILLING") in insts:
        insts[("SIT2", "BILLING")].health_status = "Degraded"
    for env_name, e in envs.items():
        for it in integrations:
            a, b = insts.get((env_name, it.upstream_id)), insts.get((env_name, it.downstream_id))
            if a and b:
                st = "broken" if (env_name == "SIT2" and it.downstream_id == "BILLING") else "connected"
                db.add(EnvironmentIntegration(environment_id=e.id, integration_id=it.id, from_instance_id=a.id,
                                              to_instance_id=b.id, status=st, last_verified=(t - 30 * day).date(),
                                              verified_by="Env Ops"))

    # Deployment history (DEP-02)
    history = {"DEV1": ["2.4.1", "2.5.0-rc1"], "SIT1": ["2.4.0", "2.4.1"], "SIT2": ["2.3.2", "2.4.0"],
               "UAT1": ["2.3.1", "2.3.2"], "PreProd": ["2.3.2"], "PERF1": ["2.3.1"]}
    for env_name, versions in history.items():
        for n, v in enumerate(versions):
            for sid in ("BILLING", "CLAIMS", "WEB"):
                i = insts.get((env_name, sid))
                if i:
                    db.add(Deployment(instance_id=i.id, environment_id=envs[env_name].id, system_id=sid, version=v,
                                      build=f"{sid.lower()}-{v}", deployed_by="ci-bot", source="ci",
                                      tool="github_actions", pipeline=f"{sid.lower()}-release",
                                      deployed_at=t - timedelta(days=10 * (len(versions) - n)), outcome="success"))

    # Bookings (BKG-*)
    def book(env, project, team, s, e, st, prio="project", by="tom.reid"):
        b = Booking(environment_id=envs[env].id, project=project, team=team, purpose=f"{project} test cycle",
                    start_at=t + s * day, end_at=t + e * day, status=st, priority=prio, requested_by=by,
                    decided_by="policy" if st in ("Approved", "Active", "Completed") else None)
        db.add(b)
        return b

    book("SIT1", "Digital Onboarding", "Team Falcon", -5, 4, "Active", by="priya.shah")
    book("SIT2", "Claims Modernisation R3", "Claims QE", -2, 9, "Active")
    book("UAT1", "Claims Modernisation R3", "Claims QE", 10, 24, "Approved")
    book("UAT1", "Renewals uplift", "Team Kestrel", 20, 30, "Requested", by="sam.lee")
    book("PreProd", "Release 2.3 dress rehearsal", "Release Mgmt", 3, 5, "Approved", "release", by="dana.okafor")
    book("SIT1", "Digital Onboarding", "Team Falcon", -40, -20, "Completed", by="priya.shah")
    book("UAT1", "Payments regression", "Payments QE", -30, -16, "Completed", by="sam.lee")

    # Calendar (DEP-07, CHG-04)
    db.add(CalendarEvent(environment_id=envs["PreProd"].id, kind="freeze", title="Quarter-end change freeze",
                         start_at=t + 6 * day, end_at=t + 13 * day, enforce=True, created_by="dana.okafor"))
    db.add(CalendarEvent(environment_id=envs["UAT1"].id, kind="refresh", title="Production-masked data refresh",
                         start_at=t + 8 * day, end_at=t + 9 * day, created_by="Env Ops"))
    db.add(CalendarEvent(environment_id=envs["PERF1"].id, kind="maintenance", title="Storage upgrade",
                         start_at=t - day, end_at=t + 2 * day, created_by="Env Ops"))
    db.add(CalendarEvent(environment_id=None, kind="release", title="Release 2.4 to production",
                         start_at=t + 15 * day, end_at=t + 15 * day + timedelta(hours=4), created_by="Release Mgmt"))

    # Issues (CHG-*)
    db.add(Issue(environment_id=envs["SIT2"].id, instance_id=insts.get(("SIT2", "BILLING")).id if insts.get(("SIT2", "BILLING")) else None,
                 title="Billing responses slow (>5s) after MQ hub patch", severity="high", status="in_progress",
                 owner="Env Ops", category="infrastructure", known_issue=True,
                 workaround="Run billing tests outside 10:00–12:00 batch window", external_system="servicenow",
                 external_ref="INC0012345", kind="incident", opened_at=t - 2 * day, sla_due_at=t - day,
                 hours_lost=6, created_by="tom.reid"))
    db.add(Issue(environment_id=envs["PERF1"].id, title="Storage array maintenance overran", severity="critical",
                 status="open", owner="Infra", category="infrastructure", kind="incident", opened_at=t - day,
                 sla_due_at=t - day + timedelta(hours=4), created_by="dana.okafor"))
    db.add(Issue(environment_id=envs["UAT1"].id, title="Test user accounts expire every 30 days", severity="low",
                 status="open", category="access", known_issue=True, workaround="Ask Env Ops to reset via ticket",
                 opened_at=t - 12 * day, sla_due_at=t - 2 * day, created_by="sam.lee"))

    # Health history for availability (HLT-05)
    for env_name, e in envs.items():
        if env_name == "TRN1":
            continue
        db.add(HealthResult(environment_id=e.id, status="Healthy", checked_at=t - 30 * day, source="seed"))
        if env_name == "SIT2":
            db.add(HealthResult(environment_id=e.id, status="Down", checked_at=t - 12 * day, source="seed"))
            db.add(HealthResult(environment_id=e.id, status="Healthy", checked_at=t - 12 * day + timedelta(hours=5),
                                source="seed"))
            db.add(HealthResult(environment_id=e.id, status="Degraded", checked_at=t - 2 * day, source="seed"))
        if env_name == "PERF1":
            db.add(HealthResult(environment_id=e.id, status="Down", checked_at=t - day, source="seed"))

    # Configuration (CFG-*, SEC-*)
    for k, v, d in [("LOG_LEVEL", "INFO", "Default log level"), ("HTTP_TIMEOUT_MS", "30000", "Outbound HTTP timeout"),
                    ("FEATURE_NEW_CLAIMS_UI", "false", "Feature flag")]:
        db.add(Variable(environment_id=None, key=k, value=v, description=d, owner="Platform Team",
                        value_type="number" if k.endswith("_MS") else ("boolean" if k.startswith("FEATURE") else "string")))
    for env_name, e in envs.items():
        if env_name == "TRN1":
            continue
        base = f"https://api.{env_name.lower()}.example.internal"
        rows = [("API_BASE_URL", base, False, None, "url"), ("DB_HOST", f"db-{env_name.lower()}.example.internal", False,
                                                             None, "string"),
                ("DB_PASSWORD", "", True, f"kv://envmgmt-{env_name.lower()}/db-password", "string"),
                ("MQ_QUEUE_MANAGER", "QM_HUB01" if env_name in ("SIT1", "SIT2") else f"QM_{env_name}", False, None, "string")]
        if env_name in ("DEV1", "SIT1"):
            rows.append(("LOG_LEVEL", "DEBUG", False, None, "string"))
        if env_name == "SIT2":
            rows.append(("FEATURE_NEW_CLAIMS_UI", "true", False, None, "boolean"))
        for k, v, secret, ref, vt in rows:
            db.add(Variable(environment_id=e.id, key=k, value=v, is_secret=secret, vault_ref=ref, value_type=vt,
                            sensitivity="restricted" if secret else "internal", owner="Env Ops",
                            last_rotated_at=t - 80 * day if secret else None,
                            rotation_due_at=(t + 10 * day if env_name != "SIT2" else t - 3 * day) if secret else None,
                            rotation_owner="Env Ops" if secret else None))
    for typ, k, secret in [("*", "API_BASE_URL", False), ("*", "DB_HOST", False), ("*", "DB_PASSWORD", True),
                           ("UAT", "AUDIT_SINK_URL", False), ("PreProd", "AUDIT_SINK_URL", False)]:
        db.add(ConfigTemplateKey(env_type=typ, key=k, required=True, is_secret=secret,
                                 description=f"Required for {typ if typ != '*' else 'every'} environment"))

    # Test data (TDM-*)
    ds = TestDataSet(environment_id=envs["UAT1"].id, name="Masked policy book (Oct)", source="Production copy",
                     volume="1.2M policies", refresh_date=(t - 20 * day).date(), masking_status="masked",
                     production_derived=True, owner="Data Services", system_id="POLISY")
    db.add(ds)
    db.add(TestDataSet(environment_id=envs["SIT2"].id, name="Synthetic claims pack", source="Generated",
                       volume="50k claims", refresh_date=(t - 100 * day).date(), masking_status="synthetic",
                       owner="Claims QE", system_id="CLAIMS"))
    db.flush()
    db.add(DataJob(dataset_id=ds.id, kind="refresh", status="succeeded", owner="Data Services",
                   started_at=t - 20 * day, finished_at=t - 20 * day + timedelta(hours=6)))
    db.add(DataJob(dataset_id=ds.id, kind="refresh", status="scheduled", owner="Data Services",
                   started_at=t + 8 * day))

    db.add(PromotionPath(name="Core release train", description="DEV → SIT → UAT → PreProd",
                         stages=[{"environment_id": envs[n].id, "gate_status": g, "gate_note": None}
                                 for n, g in [("DEV1", "passed"), ("SIT1", "passed"), ("UAT1", "open"),
                                              ("PreProd", "open")]]))
    audit(db, user, "sample_data", "environment", None, {"environments": len(envs)})
    db.flush()
    return {"environments": len(envs), "instances": len({id(i) for i in insts.values()})}
