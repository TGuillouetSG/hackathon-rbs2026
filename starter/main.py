"""Run the Foundry CSV analysis agent from the command line."""

import argparse
import json
import logging
from pathlib import Path

from client import FoundryClient
from csv_agent import CsvAnalysisAgent


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Analyze a CSV with locally executed Python")
    parser.add_argument("csv_file", type=Path, help="CSV input (up to 10 MiB)")
    parser.add_argument("objective", help="Business question or analysis objective")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent / "output")
    args = parser.parse_args()

    client = FoundryClient()
    result = CsvAnalysisAgent(foundry_client=client).run(args.csv_file, args.objective, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
