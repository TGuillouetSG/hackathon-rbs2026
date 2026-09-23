"""A fixed LangGraph workflow: aggregation -> summary."""

import uuid
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

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
    report: Dict[str, Any]


class CsvAnalysisAgent:
    def __init__(self, *, foundry_client: Optional[FoundryClient] = None):
        foundry = foundry_client if foundry_client is not None else FoundryClient()
        self.model = foundry.deployment_name
        implementation = CsvTools(foundry)
        self.aggregation_tool = StructuredTool.from_function(implementation.aggregate)
        self.summary_tool = StructuredTool.from_function(implementation.summarize)
        graph = StateGraph(CsvState)
        graph.add_node("aggregation", self._aggregate)
        graph.add_node("summary", self._summarize)
        graph.add_edge(START, "aggregation")
        graph.add_edge("aggregation", "summary")
        graph.add_edge("summary", END)
        self.graph = graph.compile()

    def _aggregate(self, state: CsvState) -> dict:
        return self.aggregation_tool.invoke({
            "csv_path": state["csv_path"], "objective": state["objective"],
            "run_dir": state["run_dir"],
        })

    def _summarize(self, state: CsvState) -> dict:
        return self.summary_tool.invoke({
            "aggregation_path": state["aggregation_path"], "objective": state["objective"],
        })

    def run(self, csv_path: Path, objective: str, output_dir: Path) -> Dict[str, Any]:
        source = import_csv(csv_path)
        if not objective.strip():
            raise ValueError("Analysis objective cannot be empty")
        run_dir = Path(output_dir).resolve() / uuid.uuid4().hex
        run_dir.mkdir(parents=True, exist_ok=False)
        result = self.graph.invoke({
            "csv_path": str(source), "objective": objective, "run_dir": str(run_dir),
        })
        return {key: result[key] for key in (
            "run_dir", "script_path", "aggregation_path", "report_path", "report",
        )}
