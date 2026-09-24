"""Checks the appointment workflow's CSV agent integration."""

import json
import time
import unittest
from unittest.mock import patch

from server.app import STARTER_DIR, _appointment_report, app

TOPICS = [
    {
        "Insight": f"Enseignement {index}.",
        "Signal_in_the_data": f"Signal {index}.",
        "details": f"Détails {index}.",
    }
    for index in range(1, 4)
]


class RdvWorkflowTests(unittest.TestCase):
    def test_workflow_streams_agent_report(self):
        report = {"selected_aggregates": {"count": "3"}, "items": TOPICS}
        with (
            patch("server.app._appointment_report", return_value=report) as run,
            self.assertLogs(app.logger.name, level="INFO") as logs,
        ):
            response = app.test_client().post("/api/rdv/workflow")
            events = [
                json.loads(line[6:])
                for line in response.get_data(as_text=True).splitlines()
                if line.startswith("data: ")
            ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(events[-2]["step"], "brief")
        self.assertEqual(events[-2]["report"], report)
        self.assertEqual(events[-1], {"status": "done"})
        run.assert_called_once()
        self.assertTrue(any("RDV workflow started" in line for line in logs.output))
        self.assertTrue(
            any(
                "RDV workflow completed" in line and "topic_count=3" in line
                for line in logs.output
            )
        )

    def test_slow_analysis_emits_progress_before_completion(self):
        def slow_topics(customer_id, on_step=None):
            on_step("profile")
            on_step("write")
            time.sleep(0.05)
            return {"items": TOPICS}

        with (
            patch("server.app._appointment_report", side_effect=slow_topics),
            patch("server.app.WORKFLOW_HEARTBEAT_SECONDS", 0.01, create=True),
        ):
            response = app.test_client().post("/api/rdv/workflow")
            events = [
                json.loads(line[6:])
                for line in response.get_data(as_text=True).splitlines()
                if line.startswith("data: ")
            ]
        context_events = [item for item in events if item.get("step") == "context"]
        self.assertTrue(
            any(
                item.get("message")
                for item in context_events
                if item["status"] == "running"
            )
        )
        self.assertEqual(context_events[-1]["status"], "complete")

    def test_stream_steps_follow_graph_nodes(self):
        def graph_topics(customer_id, on_step=None):
            for node in ("profile", "write", "execute", "summary"):
                on_step(node)
            return {"items": TOPICS}

        with patch("server.app._appointment_report", side_effect=graph_topics):
            response = app.test_client().post("/api/rdv/workflow")
            events = [
                json.loads(line[6:])
                for line in response.get_data(as_text=True).splitlines()
                if line.startswith("data: ")
            ]
        transitions = [
            (item.get("step"), item["status"]) for item in events if item.get("step")
        ]
        self.assertEqual(
            transitions,
            [
                ("client", "running"),
                ("client", "running"),
                ("client", "complete"),
                ("context", "running"),
                ("context", "running"),
                ("context", "complete"),
                ("brief", "running"),
                ("brief", "complete"),
            ],
        )

    def test_agent_uses_tiny_ex_input_and_objective_without_truncating_report(self):
        report = {
            "report": {
                "selected_aggregates": {"count": "3"},
                "items": TOPICS + [{
                    "Insight": "Extra",
                    "Signal_in_the_data": "Signal extra.",
                    "details": "Détails extra.",
                }],
            }
        }
        with (
            patch("csv_agent.CsvAnalysisAgent") as agent,
            self.assertLogs(app.logger.name, level="INFO") as logs,
        ):
            agent.return_value.run.return_value = report
            self.assertEqual(
                _appointment_report("annie"),
                report["report"],
            )
            self.assertEqual(
                _appointment_report("marc"),
                report["report"],
            )
        self.assertTrue(
            any(
                "LangGraph agent returned to RDV API" in line
                and "item_count=4" in line
                for line in logs.output
            )
        )
        self.assertEqual(
            agent.return_value.run.call_args_list[0].args[0],
            STARTER_DIR / "inputs" / "client-002.csv",
        )
        self.assertEqual(
            agent.return_value.run.call_args_list[1].args[0],
            STARTER_DIR / "data" / "marc_account_operations.csv",
        )
        from config import settings

        self.assertEqual(
            agent.return_value.run.call_args_list[0].args[1],
            settings.agent.objective,
        )
        self.assertEqual(
            agent.return_value.run.call_args_list[1].args[1],
            settings.agent.objective,
        )
        self.assertEqual(
            agent.return_value.run.call_args_list[0].args[2],
            STARTER_DIR / "output" / "rdv" / "annie",
        )
        self.assertEqual(
            agent.return_value.run.call_args_list[1].args[2],
            STARTER_DIR / "output" / "rdv" / "marc",
        )

    def test_one_supported_topic_does_not_require_three(self):
        report = {"report": {"items": TOPICS[:1]}}
        with patch("csv_agent.CsvAnalysisAgent") as agent:
            agent.return_value.run.return_value = report
            self.assertEqual(_appointment_report(), {"items": TOPICS[:1]})

        with patch("server.app._appointment_report", return_value={"items": TOPICS[:1]}):
            response = app.test_client().post("/api/rdv/workflow")
            events = [
                json.loads(line[6:])
                for line in response.get_data(as_text=True).splitlines()
                if line.startswith("data: ")
            ]
        self.assertEqual(events[-2]["status"], "complete")
        self.assertEqual(events[-2]["report"], {"items": TOPICS[:1]})
        self.assertNotIn("warning", events[-2])
        self.assertEqual(events[-1], {"status": "done"})

    def test_agent_returns_no_topics_without_demo_fallback(self):
        with patch("csv_agent.CsvAnalysisAgent") as agent:
            agent.return_value.run.return_value = {"report": {"items": []}}
            self.assertEqual(_appointment_report("annie"), {"items": []})
            self.assertEqual(_appointment_report("marc"), {"items": []})

    def test_invalid_generated_aggregation_reports_error(self):
        failure = RuntimeError(
            "CSV analysis failed after one generation: "
            "Invalid or missing aggregation.csv: Aggregation CSV has no results"
        )
        with (
            patch("csv_agent.CsvAnalysisAgent") as agent,
            self.assertLogs(app.logger.name, level="ERROR") as logs,
        ):
            agent.return_value.run.side_effect = failure
            response = app.test_client().post("/api/rdv/workflow?customer=annie")
            events = [
                json.loads(line[6:])
                for line in response.get_data(as_text=True).splitlines()
                if line.startswith("data: ")
            ]
        self.assertEqual(events[-1]["status"], "error")
        self.assertNotIn("report", events[-1])
        self.assertTrue(any("RDV workflow failed" in line for line in logs.output))

    def test_no_complete_topics_still_finishes_with_warning(self):
        with (
            patch("server.app._appointment_report", return_value={"items": []}),
            self.assertLogs(app.logger.name, level="WARNING") as logs,
        ):
            response = app.test_client().post("/api/rdv/workflow")
            events = [
                json.loads(line[6:])
                for line in response.get_data(as_text=True).splitlines()
                if line.startswith("data: ")
            ]
        self.assertEqual(events[-2]["report"], {"items": []})
        self.assertEqual(
            events[-2]["warning"],
            "Aucun sujet étayé n'a été trouvé dans les opérations.",
        )
        self.assertEqual(events[-1], {"status": "done"})
        self.assertTrue(any("topic_count=0" in line for line in logs.output))

    def test_workflow_failure_is_logged(self):
        with (
            patch(
                "server.app._appointment_report", side_effect=ValueError("CSV missing")
            ),
            self.assertLogs(app.logger.name, level="ERROR") as logs,
        ):
            response = app.test_client().post("/api/rdv/workflow")
            events = [
                json.loads(line[6:])
                for line in response.get_data(as_text=True).splitlines()
                if line.startswith("data: ")
            ]
        self.assertEqual(events[-1], {"status": "error", "message": "CSV missing"})
        self.assertTrue(any("RDV workflow failed" in line for line in logs.output))

    def test_customer_routes_preserve_selection_and_reject_unknown_ids(self):
        client = app.test_client()
        default = client.get("/").get_data(as_text=True)
        marc = client.get("/?customer=marc").get_data(as_text=True)
        rdv = client.get("/rdv?customer=marc").get_data(as_text=True)
        self.assertIn("Mme Françoise Martin", default)
        self.assertIn("M. Marc DELORME", marc)
        self.assertNotIn("<strong>Mme Françoise Martin</strong>", marc)
        self.assertNotIn("Risque de pli non distribué", marc)
        self.assertIn("/rdv?customer=marc", marc)
        self.assertIn("M. Marc DELORME", rdv)
        self.assertNotIn("Françoise Martin", rdv)
        self.assertIn("Projet immobilier possible", rdv)
        self.assertNotIn("Adresse à mettre à jour", rdv)
        self.assertIn('id="workflow-result" aria-labelledby=', rdv)
        self.assertIn("/?customer=marc", rdv)
        self.assertEqual(client.get("/?customer=missing").status_code, 404)
        self.assertEqual(client.get("/rdv?customer=missing").status_code, 404)
        self.assertEqual(
            client.post("/api/rdv/workflow?customer=missing").status_code, 404
        )

    def test_workflow_receives_selected_customer(self):
        with patch("server.app._appointment_report", return_value={"items": TOPICS}) as analyze:
            app.test_client().post("/api/rdv/workflow?customer=marc").get_data()
        self.assertEqual(analyze.call_args.args[0], "marc")

    def test_unknown_customer_cannot_select_csv(self):
        with self.assertRaisesRegex(ValueError, "Client inconnu"):
            _appointment_report("missing")


if __name__ == "__main__":
    unittest.main()
