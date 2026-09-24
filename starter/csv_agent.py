"""LangGraph CSV agent: generate once, execute, and summarize."""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Callable, TypedDict

from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph

from client import FoundryClient
from config import settings
from csv_tools import CsvTools
from utils import import_csv

logger = logging.getLogger(__name__)


class CsvState(TypedDict, total=False):
    objective: str
    profile: dict[str, Any]
    code_id: str
    code: str
    script_path: str
    generation_seconds: float
    execution: dict[str, Any]
    error: str
    aggregation_path: str
    report_path: str
    report: dict[str, Any]


class CsvAnalysisAgent:
    def __init__(self, *, foundry_client: FoundryClient | None = None):
        self.foundry = foundry_client or FoundryClient()
        self.model = self.foundry.deployment_name

    @staticmethod
    def _prompt(state: CsvState) -> str:
        request: dict[str, Any] = {
            "objective": state["objective"],
            "profile": state["profile"],
            "task": settings.prompts.aggregation_task,
        }
        return json.dumps(request, ensure_ascii=False)

    def _make_graph(self, tools: CsvTools, on_step: Callable[[str], None] | None = None):
        write_tool = StructuredTool.from_function(tools.write_python_code)
        execute_tool = StructuredTool.from_function(tools.execute_python_code)
        summary_tool = StructuredTool.from_function(tools.summarize)
        self.write_tool = write_tool
        self.execute_tool = execute_tool
        self.summary_tool = summary_tool

        def write(state: CsvState) -> dict[str, Any]:
            if on_step:
                on_step("write")
            logger.info("Generating CSV analysis code")
            try:
                generated = write_tool.invoke({"prompt": self._prompt(state)})
                logger.info("Generated CSV analysis code (code_id=%s)", generated["code_id"])
                return {**generated, "error": ""}
            except (SyntaxError, ValueError) as exc:
                logger.warning("Code generation failed: %s", exc)
                return {"code_id": "", "error": str(exc)}

        def execute(state: CsvState) -> dict[str, Any]:
            if on_step:
                on_step("execute")
            logger.info("Executing CSV analysis code (code_id=%s)", state["code_id"])
            result = execute_tool.invoke({"code_id": state["code_id"]})
            logger.info("CSV analysis execution finished (success=%s, returncode=%s)", result["success"], result["returncode"])
            return {
                "execution": result,
                "aggregation_path": result["aggregation_path"] or "",
                "error": result["error"],
            }

        def after_write(state: CsvState) -> str:
            if state.get("code_id"):
                return "execute"
            return "failed"

        def after_execute(state: CsvState) -> str:
            if state["execution"]["success"]:
                return "summary"
            return "failed"

        def summarize(state: CsvState) -> dict[str, Any]:
            if on_step:
                on_step("summary")
            logger.info("Generating CSV analysis summary")
            return summary_tool.invoke({
                "aggregation_path": state["aggregation_path"],
                "objective": state["objective"],
            })

        graph = StateGraph(CsvState)
        graph.add_node("write", write)
        graph.add_node("execute", execute)
        graph.add_node("summary", summarize)
        graph.add_edge(START, "write")
        graph.add_conditional_edges("write", after_write, {"execute": "execute", "failed": END})
        graph.add_conditional_edges("execute", after_execute, {"summary": "summary", "failed": END})
        graph.add_edge("summary", END)
        return graph.compile()

    def run(self, csv_path: Path, objective: str, output_dir: Path,
            on_step: Callable[[str], None] | None = None) -> dict[str, Any]:
        logger.info("Starting CSV analysis for %s", csv_path)
        source = import_csv(csv_path)
        if not objective.strip():
            raise ValueError("Analysis objective cannot be empty")
        run_dir = Path(output_dir).resolve() / uuid.uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=False)
        logger.info("Created CSV analysis run directory: %s", run_dir)
        tools = CsvTools(self.foundry, run_dir, source)
        if on_step:
            on_step("profile")
        profile = tools.profile()
        graph = self._make_graph(tools, on_step=on_step)
        state = graph.invoke({"objective": objective, "profile": profile})
        if "report" not in state:
            logger.error("CSV analysis failed after one generation")
            raise RuntimeError(f"CSV analysis failed after one generation: {state.get('error', 'unknown error')}")
        logger.info("CSV analysis completed: %s", state["report_path"])
        return {
            "run_dir": str(run_dir),
            "code_id": state["code_id"],
            "script_path": state["script_path"],
            "generation_seconds": state["generation_seconds"],
            "aggregation_path": state["aggregation_path"],
            "report_path": state["report_path"],
            "report": state["report"],
            "execution": state["execution"],
        }
