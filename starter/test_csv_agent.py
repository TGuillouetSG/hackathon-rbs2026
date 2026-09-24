"""Offline tests for single-pass local code generation."""

import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

from csv_agent import CsvAnalysisAgent
from config import settings
from csv_tools import SummaryItem, SummaryOutput, CsvTools, read_aggregates


GOOD_CODE = """import csv
import os
with open(os.environ['CSV_INPUT_PATH'], newline='', encoding='utf-8') as source:
    rows = list(csv.DictReader(source))
with open(os.environ['AGGREGATION_OUTPUT_PATH'], 'w', newline='', encoding='utf-8') as target:
    writer = csv.writer(target)
    writer.writerow(['aggregate_name', 'value'])
    writer.writerow(['total_revenue', sum(int(row['revenue']) for row in rows)])
print('computed')
"""
BAD_CODE = "raise RuntimeError('broken program')\n"


class FakeResponses:
    def __init__(self, programs):
        self.programs = list(programs)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["instructions"] == settings.prompts.code_instructions:
            return SimpleNamespace(output_text=self.programs.pop(0))
        return SimpleNamespace(output_text="Voici la comparaison mensuelle par région.")

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["text_format"] is SummaryOutput
        return SimpleNamespace(output_parsed=SummaryOutput.model_validate({
            "items": [{"Insight": "Le revenu total est 5.",
                       "Signal_in_the_data": "total_revenue vaut 5."}]
        }))


class CsvAgentTests(unittest.TestCase):
    def test_summary_item_has_the_api_topic_fields(self):
        self.assertEqual(set(SummaryItem.model_fields),
                         {"Insight", "Signal_in_the_data"})
        item = SummaryItem.model_validate({
            "Insight": "Le revenu total est 5.",
            "Signal_in_the_data": "total_revenue vaut 5.",
        })
        self.assertEqual(set(item.model_dump()), {"Insight", "Signal_in_the_data"})
        with self.assertRaises(ValidationError):
            SummaryItem.model_validate({"Insight": " ",
                                        "Signal_in_the_data": "Un chiffre."})
        with self.assertRaises(ValidationError):
            SummaryItem.model_validate({"Question": "Pourquoi ?", "Insight": "Un constat.",
                                        "Signal_in_the_data": "Un chiffre."})

    def make_run(self, root, programs):
        source = root / "input.csv"
        source.write_text("revenue\n2\n3\n", encoding="utf-8")
        responses = FakeResponses(programs)
        foundry = SimpleNamespace(deployment_name="fake", client=SimpleNamespace(responses=responses))
        agent = CsvAnalysisAgent(foundry_client=foundry)
        return source, responses, agent

    def test_success_executes_saved_program_and_reports_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, [GOOD_CODE])
            result = agent.run(source, "Total revenue", root / "output")
            self.assertEqual(read_aggregates(Path(result["aggregation_path"])), {"total_revenue": "5"})
            self.assertEqual(Path(result["script_path"]).read_text(), GOOD_CODE)
            self.assertEqual(Path(result["script_path"]).stem, result["code_id"])
            self.assertEqual(result["execution"]["stdout"].strip(), "computed")
            self.assertEqual(result["execution"]["stderr"], "")
            self.assertIn("aggregation.csv", Path(result["execution"]["generated_files"][0]).name)
            self.assertEqual(result["report"]["items"][0]["Insight"], "Le revenu total est 5.")
            self.assertEqual(set(result["report"]["items"][0]),
                             {"Insight", "Signal_in_the_data"})
            self.assertGreaterEqual(result["generation_seconds"], 0)
            self.assertEqual(len(responses.calls), 2)
            self.assertTrue(all(call["store"] is False for call in responses.calls))
            self.assertEqual(responses.calls[0]["timeout"], 30)
            self.assertEqual(responses.calls[0]["max_output_tokens"], 2500)
            self.assertEqual(responses.calls[0]["reasoning"], {"effort": "low"})
            self.assertIs(responses.calls[-1]["text_format"], SummaryOutput)

    def test_progress_callback_tracks_graph_nodes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, agent = self.make_run(root, [GOOD_CODE])
            nodes = []
            agent.run(source, "Total revenue", root / "output", on_step=nodes.append)
            self.assertEqual(nodes, ["profile", "write", "execute", "summary"])

    def test_each_run_generates_fresh_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, [GOOD_CODE, GOOD_CODE])
            first = agent.run(source, "Total revenue", root / "output")
            second = agent.run(source, "Total revenue", root / "output")
            self.assertNotEqual(first["code_id"], second["code_id"])
            self.assertEqual(len([call for call in responses.calls
                                  if call.get("instructions") == settings.prompts.code_instructions]), 2)

    def test_code_generation_can_use_separate_deployment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, [GOOD_CODE])
            agent.foundry.code_deployment_name = "fast-code"
            agent.run(source, "Total revenue", root / "output")
            self.assertEqual(responses.calls[0]["model"], "fast-code")
            self.assertEqual(responses.calls[1]["model"], "fake")

    def test_execution_error_stops_after_one_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, [BAD_CODE, GOOD_CODE])
            with self.assertRaisesRegex(RuntimeError, "broken program"):
                agent.run(source, "Total revenue", root / "output")
            generation_calls = [call for call in responses.calls if call["instructions"] == settings.prompts.code_instructions]
            self.assertEqual(len(generation_calls), 1)
            self.assertEqual(len(list((root / "output").rglob("*.py"))), 1)
            self.assertFalse(list((root / "output").rglob("report.json")))

    def test_syntax_error_stops_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, ["invalid python !!!", GOOD_CODE])
            with self.assertRaisesRegex(RuntimeError, "invalid syntax"):
                agent.run(source, "Total revenue", root / "output")
            generation_calls = [call for call in responses.calls if call["instructions"] == settings.prompts.code_instructions]
            self.assertEqual(len(generation_calls), 1)
            self.assertFalse(list((root / "output").rglob("*.py")))

    def test_missing_aggregation_stops_after_one_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, ["print('no output')\n", GOOD_CODE])
            with self.assertRaisesRegex(RuntimeError, "Invalid or missing aggregation.csv"):
                agent.run(source, "Total revenue", root / "output")
            generation_calls = [call for call in responses.calls if call["instructions"] == settings.prompts.code_instructions]
            self.assertEqual(len(generation_calls), 1)

    def test_failed_execution_never_summarizes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, [BAD_CODE] * 3)
            with self.assertRaisesRegex(RuntimeError, "after one generation"):
                agent.run(source, "Total revenue", root / "output")
            self.assertEqual(len(responses.calls), 1)
            self.assertFalse(list((root / "output").rglob("report.json")))

    def test_code_id_is_scoped_to_its_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, agent = self.make_run(root, [GOOD_CODE])
            tools = CsvTools(agent.foundry, root / "run", source)
            generated = tools.write_python_code("Compute revenue")
            with self.assertRaisesRegex(ValueError, "Invalid code_id"):
                tools.execute_python_code("../analysis.py")
            other = CsvTools(agent.foundry, root / "other", source)
            with self.assertRaisesRegex(ValueError, "Unknown code_id"):
                other.execute_python_code(generated["code_id"])


if __name__ == "__main__":
    unittest.main()
