"""A fixed LangGraph workflow: aggregation -> summary."""

import uuid
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.tools import StructuredTool
from langgraph.graph import END, START, StateGraph

from client import FoundryClient
from csv_tools import CsvTools
from utils import import_csv


class CsvState(TypedDict, total=False):
    csv_path: str
    objective: str
    run_dir: str
    script_path: str
    aggregation_path: str
    report_path: str
    report: dict[str, Any]


class CsvAnalysisAgent:
    def __init__(self, *, foundry_client: FoundryClient | None = None):
        foundry = foundry_client or FoundryClient()
        tools = CsvTools(foundry)
        self.aggregation_tool = StructuredTool.from_function(tools.aggregate)
        self.summary_tool = StructuredTool.from_function(tools.summarize)
        graph = StateGraph(CsvState)
        graph.add_node("aggregation", self._aggregate)
        graph.add_node("summary", self._summarize)
        graph.add_edge(START, "aggregation")
        graph.add_edge("aggregation", "summary")
        graph.add_edge("summary", END)
        self.graph = graph.compile()

    def _aggregate(self, state: CsvState) -> dict[str, Any]:
        return self.aggregation_tool.invoke({
            "csv_path": state["csv_path"],
            "objective": state["objective"],
            "run_dir": state["run_dir"],
        })

    def _summarize(self, state: CsvState) -> dict[str, Any]:
        return self.summary_tool.invoke({
            "aggregation_path": state["aggregation_path"],
            "objective": state["objective"],
        })

    def run(self, csv_path: Path, objective: str, output_dir: Path) -> dict[str, Any]:
        source = import_csv(csv_path)
        if not objective.strip():
            raise ValueError("Analysis objective cannot be empty")
        run_dir = Path(output_dir).resolve() / uuid.uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=False)
        state = self.graph.invoke(
            {"csv_path": str(source), "objective": objective, "run_dir": str(run_dir)}
        )
        result_keys = (
            "run_dir", "script_path", "aggregation_path", "report_path", "report",
        )
        return {key: state[key] for key in result_keys}
