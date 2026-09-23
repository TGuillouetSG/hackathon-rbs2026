"""Small end-to-end example: uv run tiny_ex.py"""

import csv
import logging
import tempfile
from pathlib import Path

from client import FoundryClient
from csv_agent import CsvAnalysisAgent


ROWS = [
    ("2026-01", "North", 120, "C001"),
    ("2026-01", "North", 80, "C002"),
    ("2026-01", "South", 95, "C003"),
    ("2026-02", "North", 150, "C001"),
    ("2026-02", "South", 110, "C003"),
    ("2026-02", "South", 90, "C004"),
]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    client = FoundryClient()
    output_dir = Path(__file__).resolve().parent / "output"
    with tempfile.TemporaryDirectory() as temporary_dir:
        csv_path = Path(temporary_dir) / "tiny_sales.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["month", "region", "revenue", "customer_id"])
            writer.writerows(ROWS)

        result = CsvAnalysisAgent(foundry_client=client).run(
            csv_path,
            "Compare monthly revenue by region and count unique customers.",
            output_dir,
        )

    print("Aggregation:", result["aggregation_path"])
    print("Generated Python:", result["script_path"])
    print("Report:", result["report_path"])
    print("Summary:", result["report"]["summary"])
    for insight in result["report"]["insights"]:
        print("Insight:", insight)
    for question in result["report"]["questions"]:
        print("Question:", question)


if __name__ == "__main__":
    main()
