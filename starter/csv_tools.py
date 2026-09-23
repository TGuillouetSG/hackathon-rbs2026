"""CSV aggregation and summary tools using Foundry's managed Code Interpreter."""

import ast
import csv
import json
import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List

from dotenv import load_dotenv

from client import FoundryClient
from utils import import_csv

from config import settings


load_dotenv(Path(__file__).resolve().parent / ".env")
logger = logging.getLogger(__name__)

def _plain_code(text: str) -> str:
    text = text.strip()
    match = re.fullmatch(r"```(?:python)?\s*\n(.*?)\n```", text, flags=re.DOTALL | re.IGNORECASE)
    code = (match.group(1) if match else text).strip() + "\n"
    if not code.strip() or len(code.encode("utf-8")) > settings.code.max_code_bytes:
        raise ValueError("Generated Python is empty or exceeds 32 KiB")
    ast.parse(code)
    return code


def _parse_json_text(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n|\n```$", "", text, flags=re.IGNORECASE)
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")
    return result


def _code_calls(response: Any) -> List[Any]:
    return [item for item in response.output if item.type == "code_interpreter_call"]


def _profile(response: Any) -> Dict[str, Any]:
    calls = _code_calls(response)
    if not calls:
        raise RuntimeError("Foundry did not invoke Code Interpreter for profiling")
    texts = [getattr(response, "output_text", "") or ""]
    for call in calls:
        for output in getattr(call, "outputs", []) or []:
            if getattr(output, "type", None) == "logs":
                texts.append(getattr(output, "logs", "") or "")
    for value in texts:
        for line in value.splitlines():
            if "PROFILE_JSON:" in line:
                candidate = line.split("PROFILE_JSON:", 1)[1].strip()
                try:
                    profile = _parse_json_text(candidate)
                    break
                except (ValueError, json.JSONDecodeError):
                    continue
        else:
            continue
        break
    else:
        try:
            profile = _parse_json_text(texts[0])
        except (ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Foundry did not return a valid dataset profile") from exc
    if not isinstance(profile.get("row_count"), int) or profile["row_count"] < 0:
        raise ValueError("Profile has an invalid row_count")
    columns = profile.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("Profile has no columns")
    clean_columns = []
    for column in columns:
        if not isinstance(column, dict):
            raise ValueError("Profile column must be an object")
        name, dtype, missing = column.get("name"), column.get("dtype"), column.get("missing_count")
        if not isinstance(name, str) or not isinstance(dtype, str) or not isinstance(missing, int):
            raise ValueError("Profile column is missing name, dtype, or missing_count")
        if missing < 0 or missing > profile["row_count"]:
            raise ValueError("Profile has an invalid missing_count")
        clean_columns.append({"name": name, "dtype": dtype, "missing_count": missing})
    return {"row_count": profile["row_count"], "columns": clean_columns}


def _file_citations(response: Any) -> List[Any]:
    citations = []
    for item in response.output:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []) or []:
            for annotation in getattr(content, "annotations", []) or []:
                if getattr(annotation, "type", None) == "container_file_citation":
                    citations.append(annotation)
    return citations


def read_aggregates(path: Path) -> Dict[str, str]:
    if path.stat().st_size > settings.code.max_aggregation_bytes:
        raise ValueError("Aggregation CSV exceeds 1 MiB")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["aggregate_name", "value"]:
            raise ValueError("Aggregation CSV must have exactly aggregate_name,value columns")
        values = {}
        for row in reader:
            if len(values) >= settings.code.max_aggregates:
                raise ValueError("Aggregation CSV exceeds 1000 results")
            if None in row or row["aggregate_name"] is None or row["value"] is None:
                raise ValueError("Aggregation CSV rows must have exactly two fields")
            name = row["aggregate_name"]
            value = row["value"]
            if not name or name != name.strip() or name in values:
                raise ValueError("Aggregate names must be nonempty and unique")
            try:
                number = Decimal(value)
            except (InvalidOperation, TypeError) as exc:
                raise ValueError("Aggregate values must be numeric") from exc
            if not number.is_finite():
                raise ValueError("Aggregate values must be finite")
            values[name] = value
    if not values:
        raise ValueError("Aggregation CSV has no results")
    return values


class CsvTools:
    def __init__(self, foundry: FoundryClient):
        self.model = foundry.deployment_name
        self.openai = foundry.client

    def _respond(self, file_ids: List[str], instructions: str, message: str) -> Any:
        return self.openai.responses.create(
            model=self.model, instructions=instructions, input=message, store=False,
            tools=[{"type": "code_interpreter", "container": {
                "type": "auto", "file_ids": file_ids,
            }}],
            tool_choice={"type": "code_interpreter"},
        )

    def _cleanup(self, file_ids: List[str]) -> None:
        for file_id in file_ids:
            try:
                self.openai.files.delete(file_id)
            except Exception:
                logger.warning("Uploaded file cleanup failed", exc_info=True)

    def _generate_code(self, profile: Dict[str, Any], objective: str, error: str = "") -> str:
        started = perf_counter()
        logger.info("Generating analysis.py from the dataset profile")
        response = self.openai.responses.create(
            model=self.model, store=False,
            instructions=settings.prompts.aggregation_prompt,
            input=json.dumps({"objective": objective, "profile": profile, "previous_error": error}),
        )
        code = _plain_code(response.output_text)
        logger.info("Generated and validated Python in %.1fs (%d bytes)",
                    perf_counter() - started, len(code.encode("utf-8")))
        return code

    def _download_aggregation(self, response: Any, path: Path) -> None:
        citations = [
            item for item in _file_citations(response)
            if Path(item.filename).name == "aggregation.csv"
        ]
        if not citations:
            raise RuntimeError("Foundry did not cite aggregation.csv as a generated file")
        citation = citations[-1]
        logger.info("Downloading aggregation.csv from Code Interpreter")
        content = self.openai.containers.files.content.retrieve(
            file_id=citation.file_id, container_id=citation.container_id
        )
        path.write_bytes(content.read())
        aggregates = read_aggregates(path)
        logger.info("Saved and validated %d aggregates: %s", len(aggregates), path)

    @staticmethod
    def _check_uploaded_script_was_run(response: Any) -> None:
        calls = _code_calls(response)
        if not calls:
            raise RuntimeError("Foundry did not execute Code Interpreter")
        if not any("analysis.py" in (getattr(call, "code", "") or "") for call in calls):
            raise RuntimeError("Code Interpreter did not reference the uploaded analysis.py")

    def summarize(self, aggregation_path: str, objective: str) -> Dict[str, Any]:
        """Read saved aggregates and create a report using the dedicated summary prompt."""
        path = Path(aggregation_path)
        selected = read_aggregates(path)
        started = perf_counter()
        logger.info("Generating report from %d selected aggregates", len(selected))
        response = self.openai.responses.create(
            model=self.model, store=False,
            instructions=settings.prompts.summary_system_prompt,
            input=json.dumps({"objective": objective, "aggregates": selected}),
        )
        report = _parse_json_text(response.output_text)
        if not isinstance(report.get("summary"), str):
            raise ValueError("Analysis report is missing a summary")
        for key in ("questions", "insights"):
            if not isinstance(report.get(key), list) or not all(
                isinstance(value, str) for value in report[key]
            ):
                raise ValueError("Analysis report is missing " + key)
        logger.info("Report validated in %.1fs: %d insights, %d questions",
                    perf_counter() - started, len(report["insights"]), len(report["questions"]))
        report = {"selected_aggregates": selected, "summary": report["summary"],
                  "questions": report["questions"], "insights": report["insights"],
                  "final_answer": report["summary"]}
        report_path = path.with_name("report.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"report_path": str(report_path), "report": report}

    def aggregate(self, csv_path: str, objective: str, run_dir: str) -> Dict[str, str]:
        """Generate Python, execute it in Foundry, and save the aggregation CSV."""
        source = import_csv(Path(csv_path))
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        file_ids = []
        try:
            with source.open("rb") as handle:
                uploaded = self.openai.files.create(purpose="assistants", file=handle)
            file_ids.append(uploaded.id)
            logger.info("Profiling CSV schema with Code Interpreter")
            profile = _profile(self._respond(
                [uploaded.id], settings.prompts.code_interpreter_profile_instructions, "Profile the attached source CSV.",
            ))
            (run_dir / "profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
            error = ""
            for attempt in range(settings.code.max_repairs + 1):
                logger.info("Aggregation attempt %d/%d", attempt + 1, settings.code.max_repairs + 1)
                script = run_dir / "analysis.py"
                try:
                    script.write_text(self._generate_code(profile, objective, error), encoding="utf-8")
                    with script.open("rb") as handle:
                        script_file = self.openai.files.create(purpose="assistants", file=handle)
                    file_ids.append(script_file.id)
                    response = self._respond(
                        [uploaded.id, script_file.id], settings.promptscode_interpreter_execution_instructions,
                        "Execute the uploaded analysis.py exactly as provided. "
                        "Cite the generated aggregation.csv file.",
                    )
                    self._check_uploaded_script_was_run(response)
                    aggregation = run_dir / "aggregation.csv"
                    self._download_aggregation(response, aggregation)
                except (SyntaxError, RuntimeError, ValueError) as exc:
                    logger.warning("Code or aggregation validation failed (%s); %s",
                                   type(exc).__name__,
                                   "no attempts remain" if attempt == settings.code.max_repairs else "regenerating script")
                    if attempt == settings.code.max_repairs:
                        raise
                    error = str(exc)[:500]
                    continue
                return {"script_path": str(script), "aggregation_path": str(aggregation)}
            raise RuntimeError("Aggregation failed")
        finally:
            self._cleanup(file_ids)
