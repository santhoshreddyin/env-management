"""Cross-entity validation of an integration dataset (FR-11).

Row-level type checks happen while parsing (see excel.py). This module checks
references, duplicates, hop sequences and orphans across the whole dataset.
Errors block an import or edit; warnings are reported but accepted.
"""

from collections import defaultdict
from collections.abc import Callable

from app.flows.config import get_flow_config
from app.flows.schemas import Dataset, HopIn, ValidationIssue

SYSTEMS, INTEGRATIONS, HOPS, DETAILS = "Systems", "Integrations", "Hops", "ComponentDetails"

# Maps (sheet, index within that sheet's list) -> Excel row number. None when not from Excel.
RowLocator = Callable[[str, int], int | None]


def validate_dataset(ds: Dataset, row_of: RowLocator | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def add(severity, sheet, idx, column, message, ref=None):
        row = row_of(sheet, idx) if (row_of and idx is not None) else None
        issues.append(
            ValidationIssue(severity=severity, sheet=sheet, row=row, column=column, ref=ref, message=message)
        )

    cfg = get_flow_config()

    # --- Systems ----------------------------------------------------------------------
    system_ids: set[str] = set()
    names: dict[str, str] = {}
    for i, s in enumerate(ds.systems):
        if s.id in system_ids:
            add("error", SYSTEMS, i, "id", f"Duplicate system id '{s.id}'", s.id)
        system_ids.add(s.id)
        key = s.name.lower()
        if key in names and names[key] != s.id:
            add("error", SYSTEMS, i, "name", f"Duplicate system name '{s.name}' (also used by '{names[key]}')", s.id)
        names.setdefault(key, s.id)
        if s.layer and s.layer not in cfg.layer_ids:
            add("error", SYSTEMS, i, "layer",
                f"Unknown layer '{s.layer}'. Expected one of: {', '.join(cfg.layer_ids)}", s.id)

    # --- Integrations -----------------------------------------------------------------
    integrations: dict[str, int] = {}
    for i, it in enumerate(ds.integrations):
        if it.id in integrations:
            add("error", INTEGRATIONS, i, "id", f"Duplicate integration id '{it.id}'", it.id)
        else:
            integrations[it.id] = i
        for col in ("upstream_id", "downstream_id"):
            ref = getattr(it, col)
            if ref not in system_ids:
                add("error", INTEGRATIONS, i, col, f"Unknown system '{ref}'", it.id)
        if it.upstream_id == it.downstream_id:
            add("warning", INTEGRATIONS, i, "downstream_id", "Upstream and downstream are the same system", it.id)

    # --- Hops -------------------------------------------------------------------------
    hops_by_integration: dict[str, list[tuple[int, HopIn]]] = defaultdict(list)
    for i, h in enumerate(ds.hops):
        ref = f"{h.integration_id}#{h.sequence}"
        if h.integration_id not in integrations:
            add("error", HOPS, i, "integration_id", f"Unknown integration '{h.integration_id}'", ref)
        for col in ("from_system", "to_system"):
            sid = getattr(h, col)
            if sid not in system_ids:
                add("error", HOPS, i, col, f"Unknown system '{sid}'", ref)
        if h.from_system == h.to_system:
            add("error", HOPS, i, "to_system", "A hop cannot start and end at the same system", ref)
        if h.protocol == "MQ" and not h.queue_name:
            add("warning", HOPS, i, "queue_name", "MQ hop has no queue name", ref)
        hops_by_integration[h.integration_id].append((i, h))

    for iid, idx in integrations.items():
        it = ds.integrations[idx]
        entries = sorted(hops_by_integration.get(iid, []), key=lambda e: e[1].sequence)
        if not entries:
            add("error", INTEGRATIONS, idx, "id", f"Integration '{iid}' has no hops", iid)
            continue

        seen: set[int] = set()
        for i, h in entries:
            if h.sequence in seen:
                add("error", HOPS, i, "sequence", f"Duplicate sequence {h.sequence} in integration '{iid}'",
                    f"{iid}#{h.sequence}")
            seen.add(h.sequence)
        expected = 1
        for i, h in entries:
            if h.sequence in (expected - 1,):  # duplicate, already reported
                continue
            if h.sequence != expected:
                add("error", HOPS, i, "sequence",
                    f"Broken sequence in integration '{iid}': expected {expected}, found {h.sequence}",
                    f"{iid}#{h.sequence}")
            expected = h.sequence + 1

        ordered = [h for _, h in entries]
        for (i, cur), prev in zip(entries[1:], ordered[:-1]):
            if prev.to_system != cur.from_system:
                add("warning", HOPS, i, "from_system",
                    f"Hop {cur.sequence} starts at '{cur.from_system}' but hop {prev.sequence} "
                    f"ended at '{prev.to_system}'", f"{iid}#{cur.sequence}")
        requests = [(i, h) for i, h in entries if h.direction == "request"]
        if requests:
            first_i, first = requests[0]
            if first.from_system != it.upstream_id:
                add("warning", HOPS, first_i, "from_system",
                    f"First request hop of '{iid}' starts at '{first.from_system}', "
                    f"not at the upstream '{it.upstream_id}'", f"{iid}#{first.sequence}")
            last_i, last = requests[-1]
            if last.to_system != it.downstream_id:
                add("warning", HOPS, last_i, "to_system",
                    f"Last request hop of '{iid}' ends at '{last.to_system}', "
                    f"not at the downstream '{it.downstream_id}'", f"{iid}#{last.sequence}")

    # --- Component details ------------------------------------------------------------
    for i, d in enumerate(ds.component_details):
        if d.system_id not in system_ids:
            add("error", DETAILS, i, "system_id", f"Unknown system '{d.system_id}'", d.system_id)

    # --- Orphans ----------------------------------------------------------------------
    used = {it.upstream_id for it in ds.integrations} | {it.downstream_id for it in ds.integrations}
    used |= {h.from_system for h in ds.hops} | {h.to_system for h in ds.hops}
    for i, s in enumerate(ds.systems):
        if s.id not in used:
            add("warning", SYSTEMS, i, "id", f"Orphan system '{s.id}' is not used by any integration or hop", s.id)

    return issues


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(i.severity == "error" for i in issues)
