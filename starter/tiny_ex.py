"""Small end-to-end example: uv run tiny_ex.py"""

import csv
import logging
import tempfile
from pathlib import Path

from client import FoundryClient
from csv_agent import CsvAnalysisAgent
from config import settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    client_number = "1"

    client = FoundryClient()
    output_dir = Path(__file__).resolve().parent / "output"
    csv_path = (
        Path(__file__).resolve().parent / "inputs" / f"client-00{client_number}.csv"
    )

    result = CsvAnalysisAgent(foundry_client=client).run(
        # "Gestion d'un litige lié à une fraude à la carte bancaire avec contestation de frais d'incident",
        "Restructurer les crédits conso",
        csv_path,
        settings.agent.objective,
        output_dir,
    )

    print("Aggregation:", result["aggregation_path"])
    print("Generated Python:", result["script_path"])
    print("Report:", result["report_path"])
    print("======================================")
    for item in result["report"]["items"]:
        print("Insight:", item["Insight"])
        print("Signal in the data:", item["Signal_in_the_data"])
        print("Details:", item["details"])
        print("======================================")

    print(result["report"]["steps_to_suggest"])


if __name__ == "__main__":
    main()
