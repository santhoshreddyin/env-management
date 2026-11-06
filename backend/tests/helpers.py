from io import BytesIO

from openpyxl import load_workbook

from app.flows.excel import build_workbook
from app.flows.sample_data import sample_dataset

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def sample_workbook(mutate=None) -> bytes:
    """Sample workbook bytes, optionally edited with mutate(workbook)."""
    content = build_workbook(sample_dataset())
    if mutate is None:
        return content
    wb = load_workbook(BytesIO(content))
    mutate(wb)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload(client, content: bytes, dry_run=False, name="flows.xlsx"):
    return client.post(f"/api/import?dry_run={str(dry_run).lower()}", files={"file": (name, content, XLSX)})
