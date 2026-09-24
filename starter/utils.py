from pathlib import Path

MAX_CSV_BYTES = 10 * 1024 * 1024

def import_csv(csv_path:Path):
    source = Path(csv_path).resolve()
    if not source.is_file() or source.suffix.lower() != ".csv":
        raise ValueError("Input must be an existing CSV file")
    if source.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("Input CSV exceeds 10 MiB")
    return source
