"""A small, realistic sample dataset used for demos, tests and the generated sample workbook."""

from datetime import date

from app.flows.schemas import ComponentDetailIn, Dataset, HopIn, IntegrationIn, SystemIn


def _sys(id, name, type, domain, owner, layer=None, notes=None):
    return SystemIn(id=id, name=name, type=type, layer=layer, domain=domain, owner=owner,
                    environment="PROD", notes=notes)


def _hops(integration_id, *steps):
    return [
        HopIn(integration_id=integration_id, sequence=i, from_system=f, to_system=t, protocol=p,
              direction=d, queue_name=q, queue_manager=qm)
        for i, (f, t, p, d, q, qm) in enumerate(steps, start=1)
    ]


def _h(f, t, p, d="request", q=None, qm=None):
    return (f, t, p, d, q, qm)


def sample_dataset() -> Dataset:
    systems = [
        _sys("BROKER", "Broker Portal", "upstream", "Distribution", "Digital Channels"),
        _sys("WEB", "Customer Web", "upstream", "Distribution", "Digital Channels"),
        _sys("MOBILE", "Mobile App", "upstream", "Distribution", "Digital Channels"),
        _sys("CRM", "Contact Centre CRM", "upstream", "Service", "Customer Ops IT"),
        _sys("APIGW", "API Gateway", "gateway", "Integration", "Platform Team"),
        _sys("DP-EXT", "DataPower External", "gateway", "Integration", "Platform Team"),
        _sys("DP-INT", "DataPower Internal", "gateway", "Integration", "Platform Team", layer="integration"),
        _sys("ESB", "Integration Bus", "gateway", "Integration", "Platform Team", layer="integration"),
        _sys("MQHUB", "MQ Hub", "queue_manager", "Integration", "Messaging Team"),
        _sys("MFT", "MFT Server", "gateway", "Integration", "Platform Team", layer="messaging"),
        _sys("POLISY", "Polisy", "mainframe", "Policy", "Policy Admin Team", notes="Policy administration (mainframe)"),
        _sys("BILLING", "Billing", "downstream", "Finance", "Finance IT"),
        _sys("CLAIMS", "Claims", "downstream", "Claims", "Claims IT"),
        _sys("DOCS", "Document Service", "downstream", "Service", "Customer Ops IT"),
    ]

    details = [
        ComponentDetailIn(system_id="APIGW", gateway_tier="API gateway (edge)", endpoint="https://api.example.internal/"),
        ComponentDetailIn(system_id="DP-EXT", gateway_tier="DataPower tier 1 (DMZ)",
                          endpoint="dpext.example.internal:8443", notes="TLS termination, schema validation"),
        ComponentDetailIn(system_id="DP-INT", gateway_tier="DataPower tier 2 (internal)",
                          endpoint="dpint.example.internal:9443"),
        ComponentDetailIn(system_id="MQHUB", queue_references="QM_HUB01; POLICY.*, BILLING.*, CLAIMS.*",
                          notes="Central MQ hub queue manager"),
        ComponentDetailIn(system_id="POLISY", endpoint="CICS region POLPROD",
                          queue_references="POLICY.REQ, POLICY.RPY"),
        ComponentDetailIn(system_id="MFT", endpoint="mft.example.internal", notes="Nightly batch transfers"),
    ]

    integrations = [
        IntegrationIn(id="INT-001", name="Broker new business quote", journey="acquisition",
                      upstream_id="BROKER", downstream_id="POLISY", pattern="sync", primary_protocol="REST",
                      status="live", verified_by="J. Architect", last_verified=date(2026, 9, 1)),
        IntegrationIn(id="INT-002", name="Broker renewal submission", journey="renewal",
                      upstream_id="BROKER", downstream_id="POLISY", pattern="async", primary_protocol="MQ",
                      status="live", verified_by="J. Architect", last_verified=date(2026, 8, 15)),
        IntegrationIn(id="INT-003", name="Policy premium to billing", journey="renewal",
                      upstream_id="POLISY", downstream_id="BILLING", pattern="async", primary_protocol="MFT",
                      status="live", notes="Nightly batch"),
        IntegrationIn(id="INT-004", name="Customer payment", journey="servicing",
                      upstream_id="WEB", downstream_id="BILLING", pattern="sync", primary_protocol="REST",
                      status="live"),
        IntegrationIn(id="INT-005", name="First notice of loss", journey="claims",
                      upstream_id="CRM", downstream_id="CLAIMS", pattern="sync", primary_protocol="SOAP",
                      status="live"),
        IntegrationIn(id="INT-006", name="Policy documents", journey="acquisition",
                      upstream_id="POLISY", downstream_id="DOCS", pattern="async", primary_protocol="MQ",
                      status="live"),
        IntegrationIn(id="INT-007", name="Mobile policy summary", journey="servicing",
                      upstream_id="MOBILE", downstream_id="POLISY", pattern="sync", primary_protocol="REST",
                      status="planned"),
        IntegrationIn(id="INT-008", name="Claims payment", journey="claims",
                      upstream_id="CLAIMS", downstream_id="BILLING", pattern="async", primary_protocol="MQ",
                      status="live"),
    ]

    hops = [
        *_hops("INT-001",
               _h("BROKER", "APIGW", "REST"), _h("APIGW", "DP-EXT", "REST"), _h("DP-EXT", "DP-INT", "SOAP"),
               _h("DP-INT", "POLISY", "SOAP"),
               _h("POLISY", "DP-INT", "SOAP", "reply"), _h("DP-INT", "DP-EXT", "SOAP", "reply"),
               _h("DP-EXT", "APIGW", "REST", "reply"), _h("APIGW", "BROKER", "REST", "reply")),
        *_hops("INT-002",
               _h("BROKER", "APIGW", "REST"), _h("APIGW", "ESB", "REST"),
               _h("ESB", "MQHUB", "MQ", q="POLICY.RENEWAL.REQ", qm="QM_HUB01"),
               _h("MQHUB", "POLISY", "MQ", q="POLICY.RENEWAL.REQ", qm="QM_HUB01"),
               _h("POLISY", "MQHUB", "MQ", "reply", q="POLICY.RENEWAL.RPY", qm="QM_HUB01"),
               _h("MQHUB", "ESB", "MQ", "reply", q="POLICY.RENEWAL.RPY", qm="QM_HUB01")),
        *_hops("INT-003", _h("POLISY", "MFT", "MFT"), _h("MFT", "BILLING", "FILE")),
        *_hops("INT-004",
               _h("WEB", "APIGW", "REST"), _h("APIGW", "ESB", "REST"), _h("ESB", "BILLING", "REST"),
               _h("BILLING", "ESB", "REST", "reply"), _h("ESB", "APIGW", "REST", "reply"),
               _h("APIGW", "WEB", "REST", "reply")),
        *_hops("INT-005",
               _h("CRM", "DP-EXT", "SOAP"), _h("DP-EXT", "DP-INT", "SOAP"), _h("DP-INT", "CLAIMS", "SOAP"),
               _h("CLAIMS", "DP-INT", "SOAP", "reply"), _h("DP-INT", "DP-EXT", "SOAP", "reply"),
               _h("DP-EXT", "CRM", "SOAP", "reply")),
        *_hops("INT-006",
               _h("POLISY", "MQHUB", "MQ", q="DOCS.GENERATE", qm="QM_HUB01"),
               _h("MQHUB", "ESB", "MQ", q="DOCS.GENERATE", qm="QM_HUB01"), _h("ESB", "DOCS", "REST")),
        *_hops("INT-007",
               _h("MOBILE", "APIGW", "REST"), _h("APIGW", "ESB", "REST"),
               _h("ESB", "MQHUB", "MQ", q="POLICY.QUERY.REQ", qm="QM_HUB01"),
               _h("MQHUB", "POLISY", "MQ", q="POLICY.QUERY.REQ", qm="QM_HUB01"),
               _h("POLISY", "MQHUB", "MQ", "reply", q="POLICY.QUERY.RPY", qm="QM_HUB01"),
               _h("MQHUB", "ESB", "MQ", "reply", q="POLICY.QUERY.RPY", qm="QM_HUB01"),
               _h("ESB", "APIGW", "REST", "reply"), _h("APIGW", "MOBILE", "REST", "reply")),
        *_hops("INT-008",
               _h("CLAIMS", "MQHUB", "MQ", q="BILLING.CLAIMPAY", qm="QM_HUB01"),
               _h("MQHUB", "BILLING", "MQ", q="BILLING.CLAIMPAY", qm="QM_HUB01")),
    ]
    return Dataset(systems=systems, integrations=integrations, hops=hops, component_details=details)
