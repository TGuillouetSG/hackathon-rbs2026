"""Local contract tests; Azure execution is exercised by the service at runtime."""

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace as Obj
from unittest.mock import patch

from client import FoundryClient
from csv_agent import CsvAnalysisAgent
from csv_tools import read_aggregates, SUMMARY_PROMPT, AGGREGATION_PROMPT, MAX_REPAIRS


def response(output=None, text=""):
    return Obj(id="resp-" + uuid.uuid4().hex, output=output or [], output_text=text)


class FakeFiles:
    def __init__(self):
        self.created = []
        self.deleted = []

    def create(self, purpose, file):
        assert purpose == "assistants"
        file_id = "file-" + str(len(self.created) + 1)
        self.created.append((file_id, Path(file.name).name, file.read()))
        return Obj(id=file_id)

    def delete(self, file_id):
        self.deleted.append(file_id)


class FakeResponses:
    def __init__(self):
        self.calls = []
        self.deleted = []

    def delete(self, response_id):
        self.deleted.append(response_id)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = kwargs["input"]
        if not kwargs.get("tools") and "profile" in str(message):
            return response(text="import csv\nfrom pathlib import Path\n")
        if not kwargs.get("tools"):
            return response(text=json.dumps({
                "summary": "Revenue is 125000.",
                "questions": ["Why did revenue change?"],
                "insights": ["Revenue is 125000."],
            }))
        if isinstance(message, list):
            return response(text="Analysis complete.")
        if message.startswith("Profile"):
            profile = {"row_count": 1, "columns": [
                {"name": "revenue", "dtype": "int64", "missing_count": 0}
            ]}
            code = Obj(type="code_interpreter_call", outputs=[
                Obj(type="logs", logs="PROFILE_JSON:" + json.dumps(profile))
            ])
            return response(output=[code])
        if message.startswith("Execute"):
            citation = Obj(
                type="container_file_citation", filename="aggregation.csv",
                file_id="generated-file", container_id="container-1",
            )
            content = Obj(annotations=[citation])
            return response(output=[
                Obj(type="code_interpreter_call", code="runpy.run_path('/mnt/data/analysis.py')", outputs=[]),
                Obj(type="message", content=[content]),
            ])
        raise AssertionError("Unexpected request")


class CsvAgentTests(unittest.TestCase):
    def test_api_key_configuration(self):
        settings = {
            "AZURE_OPENAI_API_KEY": "test-key",
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_DEPLOYMENT_NAME": "test-model",
        }
        with patch.dict(os.environ, settings, clear=True), patch("client.OpenAI") as sdk:
            client = FoundryClient()
            sdk.assert_called_once_with(
                base_url="https://example.openai.azure.com/openai/v1", api_key="test-key"
            )
            self.assertEqual(CsvAnalysisAgent(foundry_client=client).model, "test-model")
            os.environ["AZURE_OPENAI_ENDPOINT"] = ""
            with self.assertRaisesRegex(ValueError, "AZURE_OPENAI_ENDPOINT"):
                FoundryClient()

    def test_aggregation_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aggregation.csv"
            path.write_text("aggregate_name,value\nrevenue_2026_01,125000\ncustomer_count,840\n")
            self.assertEqual(read_aggregates(path), {
                "revenue_2026_01": "125000", "customer_count": "840",
            })
            path.write_text("aggregate_name,value\ncustomer_count,1\ncustomer_count,2\n")
            with self.assertRaisesRegex(ValueError, "unique"):
                read_aggregates(path)
            path.write_text("aggregate_name,value\ncustomer_count,NaN\n")
            with self.assertRaisesRegex(ValueError, "finite"):
                read_aggregates(path)
            path.write_text("aggregate_name,value\ncustomer_count,2,extra\n")
            with self.assertRaisesRegex(ValueError, "two fields"):
                read_aggregates(path)

    def test_foundry_workflow_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "input.csv"
            source.write_text("revenue\n125000\n")
            files = FakeFiles()
            responses = FakeResponses()
            download = Obj(read=lambda: b"aggregate_name,value\nrevenue_2026_01,125000\n")
            openai = Obj(
                files=files, responses=responses,
                containers=Obj(files=Obj(content=Obj(retrieve=lambda **kwargs: download))),
            )
            with patch.dict(os.environ, {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                "AZURE_OPENAI_DEPLOYMENT_NAME": "test-model",
            }, clear=True), patch("client.OpenAI", return_value=openai):
                client = FoundryClient()
                result = CsvAnalysisAgent(foundry_client=client).run(
                    source, "Compare monthly revenue", Path(temp) / "output"
                )
            self.assertEqual(read_aggregates(Path(result["aggregation_path"])),
                             {"revenue_2026_01": "125000"})
            self.assertEqual(result["report"]["selected_aggregates"],
                             {"revenue_2026_01": "125000"})
            self.assertTrue(Path(result["script_path"]).exists())
            self.assertEqual(len(responses.deleted), 0)
            self.assertEqual(len(files.deleted), 2)
            tool_requests = [call for call in responses.calls if call.get("tools")]
            self.assertEqual(tool_requests[0]["tools"][0]["container"],
                             {"type": "auto", "file_ids": ["file-1"]})
            self.assertEqual(tool_requests[1]["tools"][0]["container"]["file_ids"],
                             ["file-1", "file-2"])
            self.assertNotIn("previous_response_id", tool_requests[1])
            self.assertEqual(len(responses.calls), 4)
            self.assertEqual(len(tool_requests), 2)
            self.assertTrue(all(call["store"] is False for call in responses.calls))
            summary = responses.calls[-1]
            self.assertEqual(summary["instructions"], SUMMARY_PROMPT)
            self.assertEqual(json.loads(summary["input"]), {
                "objective": "Compare monthly revenue",
                "aggregates": {"revenue_2026_01": "125000"},
            })
            self.assertNotIn("tools", summary)
            self.assertTrue(all("previous_response_id" not in call for call in responses.calls))
            self.assertEqual(json.loads(Path(result["report_path"]).read_text()), result["report"])
            self.assertEqual(result["report"]["final_answer"], result["report"]["summary"])

    def make_agent(self, payload=b"aggregate_name,value\nrevenue_2026_01,125000\n"):
        files, responses = FakeFiles(), FakeResponses()
        sdk = Obj(files=files, responses=responses, containers=Obj(files=Obj(
            content=Obj(retrieve=lambda **kwargs: Obj(read=lambda: payload)),
        )))
        return CsvAnalysisAgent(foundry_client=Obj(deployment_name="test-model", client=sdk)), files, responses

    def test_failed_aggregation_never_summarizes_and_cleans_uploads(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "input.csv"
            source.write_text("revenue\n125000\n")
            agent, files, responses = self.make_agent(b"aggregate_name,value\nbad,NaN\n")
            with self.assertRaisesRegex(ValueError, "finite"):
                agent.run(source, "Analyze revenue", Path(temp) / "output")
            self.assertEqual(len(files.created), MAX_REPAIRS + 2)
            self.assertEqual(files.deleted, [item[0] for item in files.created])
            self.assertFalse(any(call["instructions"] == SUMMARY_PROMPT for call in responses.calls))
            self.assertFalse(list(Path(temp).rglob("report.json")))

    def test_generated_code_is_repaired_before_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "input.csv"
            source.write_text("revenue\n125000\n")
            agent, files, responses = self.make_agent()
            original = responses.create
            failed = False

            def create(**kwargs):
                nonlocal failed
                if kwargs["instructions"] == AGGREGATION_PROMPT and not failed:
                    failed = True
                    return response(text="invalid python !!!")
                return original(**kwargs)

            with patch.object(responses, "create", side_effect=create):
                result = agent.run(source, "Analyze revenue", Path(temp) / "output")
            self.assertTrue(Path(result["report_path"]).exists())
            generated = next(call for call in responses.calls if call["instructions"] == AGGREGATION_PROMPT)
            self.assertTrue(json.loads(generated["input"])["previous_error"])
            self.assertEqual(len(files.created), 2)

    def test_summary_tool_runs_independently_and_rejects_bad_report(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "aggregation.csv"
            path.write_text("aggregate_name,value\ncount,2\n")
            agent, files, responses = self.make_agent()
            with patch.object(responses, "create", return_value=response(text='{"summary": "Two"}')):
                with self.assertRaisesRegex(ValueError, "questions"):
                    agent.summary_tool.invoke({"aggregation_path": str(path), "objective": "Explain"})
            self.assertEqual(files.created, [])
            self.assertFalse(path.with_name("report.json").exists())
            result = agent.summary_tool.invoke({"aggregation_path": str(path), "objective": "Explain"})
            self.assertEqual(result["report"]["selected_aggregates"], {"count": "2"})

    def test_empty_objective_does_not_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.csv"
            path.write_text("count\n2\n")
            agent, files, responses = self.make_agent()
            with self.assertRaisesRegex(ValueError, "objective"):
                agent.run(path, "  ", Path(temp) / "output")
            self.assertEqual(files.created, [])



if __name__ == "__main__":
    unittest.main()
