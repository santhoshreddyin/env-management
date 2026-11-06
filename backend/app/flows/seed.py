"""Seed the database with the sample dataset, or write sample/template workbooks.

    python -m app.flows.seed                  # seed if the dataset is empty
    python -m app.flows.seed --force          # replace the current dataset
    python -m app.flows.seed --with-environments  # also load the demo environment inventory
    python -m app.flows.seed --write-xlsx sample.xlsx [--template]
"""

import argparse
from pathlib import Path

import app.platform.common  # noqa: F401 - registers the audit hash-chain listener
from app.auth import User
from app.database import SessionLocal
from app.flows.excel import build_workbook
from app.flows.repository import commit_dataset, load_dataset
from app.flows.sample_data import sample_dataset
from app.flows.schemas import Dataset
from app.migrate import run_migrations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="replace existing data")
    parser.add_argument("--write-xlsx", metavar="PATH", help="write a workbook instead of seeding")
    parser.add_argument("--with-environments", action="store_true",
                        help="also load the demo environment inventory if no environments exist")
    parser.add_argument("--template", action="store_true", help="with --write-xlsx: write an empty template")
    args = parser.parse_args()

    if args.write_xlsx:
        Path(args.write_xlsx).write_bytes(build_workbook(Dataset() if args.template else sample_dataset()))
        print(f"Wrote {args.write_xlsx}")
        return

    run_migrations()
    with SessionLocal() as db:
        if load_dataset(db).systems and not args.force:
            print("Dataset not empty; use --force to replace it.")
        else:
            ds = sample_dataset()
            v = commit_dataset(db, ds, user=User("seed"), source="seed", summary="Sample dataset",
                               audit_action="seed", entity_type="dataset")
            print(f"Seeded sample dataset as version {v.id}: {ds.counts()}")
        if args.with_environments:
            from sqlalchemy import func, select

            from app.models import Environment
            from app.platform.sample import seed_platform

            if db.scalar(select(func.count()).select_from(Environment)):
                print("Environments already exist; demo inventory not loaded.")
            else:
                print(f"Seeded demo environments: {seed_platform(db)}")
                db.commit()


if __name__ == "__main__":
    main()
