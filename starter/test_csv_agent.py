"""Offline tests for the local code generation and repair loop."""

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from csv_agent import CsvAnalysisAgent
from config import settings
from csv_tools import SummaryOutput, CsvTools, read_aggregates


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
            "items": [{"Question": "Pourquoi ce total ?", "Insight": "Le revenu total est 5.",
                       "Signal_in_the_data": "total_revenue vaut 5."}]
        }))


class CsvAgentTests(unittest.TestCase):
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
            self.assertEqual(len(responses.calls), 2)
            self.assertTrue(all(call["store"] is False for call in responses.calls))
            self.assertIs(responses.calls[-1]["text_format"], SummaryOutput)

    def test_execution_error_generates_new_program_with_correction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, [BAD_CODE, GOOD_CODE])
            result = agent.run(source, "Total revenue", root / "output")
            generation_calls = [call for call in responses.calls if call["instructions"] == settings.prompts.code_instructions]
            correction = json.loads(generation_calls[1]["input"])["correction"]
            self.assertIn("broken program", correction["error"])
            self.assertEqual(correction["previous_code"], BAD_CODE)
            self.assertEqual(len(list((Path(result["run_dir"]) / "programs").glob("*.py"))), 2)
            self.assertEqual(result["report"]["selected_aggregates"], {"total_revenue": "5"})

    def test_syntax_error_is_repaired_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, ["invalid python !!!", GOOD_CODE])
            result = agent.run(source, "Total revenue", root / "output")
            generation_calls = [call for call in responses.calls if call["instructions"] == settings.prompts.code_instructions]
            self.assertIn("invalid syntax", generation_calls[1]["input"])
            self.assertEqual(len(list((Path(result["run_dir"]) / "programs").glob("*.py"))), 1)

    def test_missing_aggregation_triggers_repair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, ["print('no output')\n", GOOD_CODE])
            result = agent.run(source, "Total revenue", root / "output")
            generation_calls = [call for call in responses.calls if call["instructions"] == settings.prompts.code_instructions]
            self.assertIn("Invalid or missing aggregation.csv", generation_calls[1]["input"])
            self.assertEqual(result["report"]["selected_aggregates"], {"total_revenue": "5"})

    def test_failed_execution_never_summarizes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, responses, agent = self.make_run(root, [BAD_CODE] * 3)
            with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
                agent.run(source, "Total revenue", root / "output")
            self.assertEqual(len(responses.calls), 3)
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
