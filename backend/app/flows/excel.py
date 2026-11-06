"""Excel template, import parsing (FR-11) and export (FR-12)."""

from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import BaseModel, ValidationError

from app.flows.config import get_flow_config
from app.flows.schemas import (
    ComponentDetailIn,
    Dataset,
    Direction,
    HopIn,
    IntegrationIn,
    Pattern,
    Protocol,
    SystemIn,
    SystemType,
    ValidationIssue,
)


@dataclass(frozen=True)
class SheetSpec:
    name: str
    attr: str  # Dataset attribute
    model: type[BaseModel]
    columns: list[str]
    required: bool = True


SHEETS = [
    SheetSpec("Systems", "systems", SystemIn,
              ["id", "name", "type", "layer", "domain", "owner", "environment", "notes"]),
    SheetSpec("Integrations", "integrations", IntegrationIn,
              ["id", "name", "journey", "upstream_id", "downstream_id", "pattern", "primary_protocol",
               "status", "verified_by", "last_verified", "notes"]),
    SheetSpec("Hops", "hops", HopIn,
              ["integration_id", "sequence", "from_system", "to_system", "protocol", "direction",
               "queue_name", "queue_manager", "notes"]),
    SheetSpec("ComponentDetails", "component_details", ComponentDetailIn,
              ["system_id", "gateway_tier", "endpoint", "queue_references", "notes"], required=False),
]

WORKBOOK = "(workbook)"


def _norm_header(v: Any) -> str:
    """'Upstream ID *' -> 'upstream_id' (the template marks required columns with '*')."""
    return str(v or "").replace("*", "").strip().lower().replace(" ", "_").replace("-", "_")


def _norm_sheet(v: str) -> str:
    return v.strip().lower().replace(" ", "").replace("_", "")


def _clean_cell(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.date() if (v.hour, v.minute, v.second) == (0, 0, 0) else v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


@dataclass
class ParseResult:
    dataset: Dataset
    rows: dict[str, list[int]] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)

    def row_of(self, sheet: str, idx: int) -> int | None:
        rows = self.rows.get(sheet, [])
        return rows[idx] if idx < len(rows) else None


def parse_workbook(content: bytes) -> ParseResult:
    result = ParseResult(dataset=Dataset())

    def err(sheet, row, column, message):
        result.issues.append(ValidationIssue(severity="error", sheet=sheet, row=row, column=column, message=message))

    try:
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - openpyxl raises many different types
        err(WORKBOOK, None, None, "File is not a valid .xlsx workbook")
        return result

    try:
        by_name = {_norm_sheet(ws.title): ws for ws in wb.worksheets}
        for spec in SHEETS:
            ws = by_name.get(_norm_sheet(spec.name))
            result.rows[spec.name] = []
            if ws is None:
                if spec.required:
                    err(spec.name, None, None, f"Missing sheet '{spec.name}'")
                continue

            rows = ws.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                err(spec.name, 1, None, "Sheet is empty (no header row)")
                continue
            col_index = {_norm_header(h): i for i, h in enumerate(header) if h is not None}
            fields = spec.model.model_fields
            missing = [c for c in spec.columns if c not in col_index and fields[c].is_required()]
            for c in missing:
                err(spec.name, 1, c, f"Missing required column '{c}'")
            if missing:
                continue

            items = getattr(result.dataset, spec.attr)
            for row_no, values in enumerate(rows, start=2):
                if values is None or all(v is None or (isinstance(v, str) and not v.strip()) for v in values):
                    continue
                data = {
                    c: _clean_cell(values[col_index[c]]) if col_index[c] < len(values) else None
                    for c in spec.columns
                    if c in col_index
                }
                try:
                    items.append(spec.model.model_validate(data))
                    result.rows[spec.name].append(row_no)
                except ValidationError as e:
                    for detail in e.errors():
                        column = str(detail["loc"][0]) if detail["loc"] else None
                        value = data.get(column) if column else None
                        shown = f" (got '{value}')" if value not in (None, "") else ""
                        err(spec.name, row_no, column, f"{detail['msg']}{shown}")
    finally:
        wb.close()
    return result


# ---- Writing -------------------------------------------------------------------------------

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
VALIDATION_ROWS = 2000

INSTRUCTIONS = [
    ("Integration Flow Explorer - data template", True),
    ("", False),
    ("Fill the Systems, Integrations and Hops sheets. ComponentDetails is optional.", False),
    ("Keep the header row (row 1) unchanged. Columns marked * are required.", False),
    ("", False),
    ("Systems: one row per system. 'id' is a short stable key (e.g. SYS-POLISY); 'name' must be unique.", False),
    ("  type: upstream, downstream, gateway, queue_manager or mainframe.", False),
    ("  layer (optional): overrides the diagram layer derived from type.", False),
    ("Integrations: one row per flow. The same upstream/downstream pair may have several (one per journey).", False),
    ("  pattern: sync or async. last_verified: date of the last architect sign-off.", False),
    ("Hops: the ordered steps of each integration. sequence starts at 1 with no gaps.", False),
    ("  Each hop should start where the previous one ended. Request hops go upstream -> downstream;", False),
    ("  reply hops come back. protocol: REST, SOAP, MQ, FILE or MFT. direction: request or reply.", False),
    ("ComponentDetails: extra attributes per system, e.g. DataPower gateway tier, endpoints, queues.", False),
    ("", False),
    ("Never put credentials or payload data in this workbook - metadata only.", True),
]


def _list_validation(values: list[str]) -> DataValidation:
    return DataValidation(type="list", formula1='"' + ",".join(values) + '"', allow_blank=True)


def _ref_validation(sheet: str) -> DataValidation:
    return DataValidation(type="list", formula1=f"{sheet}!$A$2:$A${VALIDATION_ROWS}", allow_blank=True)


def _add_validation(ws, dv: DataValidation, column: str, columns: list[str]) -> None:
    letter = get_column_letter(columns.index(column) + 1)
    dv.error = "Choose a value from the list"
    dv.showErrorMessage = True
    ws.add_data_validation(dv)
    dv.add(f"{letter}2:{letter}{VALIDATION_ROWS}")


def build_workbook(ds: Dataset) -> bytes:
    cfg = get_flow_config()
    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    for i, (text, bold) in enumerate(INSTRUCTIONS, start=1):
        cell = readme.cell(row=i, column=1, value=text)
        cell.font = Font(bold=bold, size=13 if i == 1 else 11)
    readme.column_dimensions["A"].width = 110

    for spec in SHEETS:
        ws = wb.create_sheet(spec.name)
        fields = spec.model.model_fields
        for col, name in enumerate(spec.columns, start=1):
            label = name + (" *" if fields[name].is_required() else "")
            cell = ws.cell(row=1, column=col, value=label)
            cell.font, cell.fill = HEADER_FONT, HEADER_FILL
            cell.alignment = Alignment(vertical="center")
            ws.column_dimensions[get_column_letter(col)].width = max(14, len(label) + 4)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(spec.columns))}1"

        for row, item in enumerate(getattr(ds, spec.attr), start=2):
            data = item.model_dump()
            for col, name in enumerate(spec.columns, start=1):
                value = data.get(name)
                cell = ws.cell(row=row, column=col, value=value)
                if isinstance(value, date):
                    cell.number_format = "yyyy-mm-dd"

        cols = spec.columns
        if spec.name == "Systems":
            _add_validation(ws, _list_validation([t.value for t in SystemType]), "type", cols)
            _add_validation(ws, _list_validation(cfg.layer_ids), "layer", cols)
        elif spec.name == "Integrations":
            _add_validation(ws, _list_validation([p.value for p in Pattern]), "pattern", cols)
            _add_validation(ws, _list_validation([p.value for p in Protocol]), "primary_protocol", cols)
            _add_validation(ws, _ref_validation("Systems"), "upstream_id", cols)
            _add_validation(ws, _ref_validation("Systems"), "downstream_id", cols)
            dv = DataValidation(type="date", operator="greaterThan", formula1="1")
            _add_validation(ws, dv, "last_verified", cols)
        elif spec.name == "Hops":
            _add_validation(ws, _ref_validation("Integrations"), "integration_id", cols)
            dv = DataValidation(type="whole", operator="greaterThanOrEqual", formula1="1")
            _add_validation(ws, dv, "sequence", cols)
            _add_validation(ws, _ref_validation("Systems"), "from_system", cols)
            _add_validation(ws, _ref_validation("Systems"), "to_system", cols)
            _add_validation(ws, _list_validation([p.value for p in Protocol]), "protocol", cols)
            _add_validation(ws, _list_validation([d.value for d in Direction]), "direction", cols)
        elif spec.name == "ComponentDetails":
            _add_validation(ws, _ref_validation("Systems"), "system_id", cols)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
