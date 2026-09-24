from pathlib import Path
import csv
import io

MAX_CSV_BYTES = 10 * 1024 * 1024


def import_csv(csv_path: Path):
    source = Path(csv_path).resolve()
    if not source.is_file() or source.suffix.lower() != ".csv":
        raise ValueError("Input must be an existing CSV file")
    if source.stat().st_size > MAX_CSV_BYTES:
        raise ValueError("Input CSV exceeds 10 MiB")
    return source


def read_csv_rows(csv_path: Path):
    """Read common exported CSV encodings and delimiters (including French bank exports)."""
    raw = Path(csv_path).read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252")
    sample = content[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return list(csv.DictReader(io.StringIO(content, newline=""), dialect=dialect))
