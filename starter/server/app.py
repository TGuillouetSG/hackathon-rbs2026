"""Flask pages and the appointment preparation workflow."""

import json
import logging
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, abort, render_template, request

if __package__:
    from .profiles import (
        CUSTOMERS,
        DEFAULT_CUSTOMER_ID,
        customer_csv,
        profile_view,
    )
else:
    from profiles import (
        CUSTOMERS,
        DEFAULT_CUSTOMER_ID,
        customer_csv,
        profile_view,
    )

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.logger.setLevel(logging.INFO)
STARTER_DIR = Path(__file__).resolve().parents[1]
WORKFLOW_HEARTBEAT_SECONDS = 4


@app.route("/")
def index():
    customer = _selected_customer()
    return render_template(
        "index.html",
        customer=customer,
        view=profile_view(customer),
        customers=CUSTOMERS.values(),
    )


@app.route("/rdv")
def rdv():
    customer = _selected_customer()
    return render_template(
        "rdv.html",
        customer=customer,
        view=profile_view(customer),
        customers=CUSTOMERS.values(),
    )


def _selected_customer():
    customer = CUSTOMERS.get(request.args.get("customer", DEFAULT_CUSTOMER_ID))
    if customer is None:
        abort(404)
    return customer


def _appointment_report(customer_id=DEFAULT_CUSTOMER_ID, on_step=None):
    """Run the same CSV analysis as tiny_ex.py for the selected customer."""
    if str(STARTER_DIR) not in sys.path:
        sys.path.insert(0, str(STARTER_DIR))
    from config import settings
    from csv_agent import CsvAnalysisAgent

    customer = CUSTOMERS.get(customer_id)
    if customer is None:
        raise ValueError("Client inconnu.")
    csv_path = customer_csv(customer)

    report = CsvAnalysisAgent().run(
        csv_path,
        settings.agent.objective,
        STARTER_DIR / "output" / "rdv" / customer_id,
        on_step=on_step,
    )["report"]
    app.logger.info(
        "LangGraph agent returned to RDV API (item_count=%d)",
        len(report["items"]),
    )
    return report


@app.post("/api/rdv/workflow")
def rdv_workflow():
    """Stream progress and the CSV agent's appointment report."""
    customer = _selected_customer()
    customer_id = customer["id"]
    request_id = uuid.uuid4().hex
    started_at = time.monotonic()
    app.logger.info("RDV workflow started (request_id=%s)", request_id)

    def event(payload):
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def event_stream():
        try:
            updates = queue.Queue()

            def analyze():
                try:
                    report = _appointment_report(
                        customer_id, on_step=lambda node: updates.put(("node", node))
                    )
                    updates.put(("result", report))
                except Exception as exc:
                    updates.put(("error", exc))

            last_message = [
                "On rassemble les pièces du puzzle...",
                "Ils auraient pu optimiser leur démo quand même...",
                "C'est vous l'avenir !",
                "Encore un instant : On cherche du budget pour finir.",
                "Ca va vous ? Je bosse hein !",
                "On va se faire un café ?",
                "Ne touchez à rien, ça pourrait marcher.",
                "Pas trop vite le matin et doucement en démo !",
                "Rien n’est cassé. Je préfère préciser.",
                "🥱 En fait on est bien ensemble, Je vais rester un peu !",
                "Ça mouline. Avec conviction (au moins).",
                "Merci de patienter pendant qu’on invente une excellente excuse.",
            ]
            message_index = 0
            yield event(
                {
                    "step": "client",
                    "status": "running",
                    "message": last_message[message_index],
                }
            )
            threading.Thread(target=analyze, daemon=True).start()
            active_step = "client"
            while True:
                try:
                    kind, value = updates.get(timeout=WORKFLOW_HEARTBEAT_SECONDS)
                except queue.Empty:
                    message_index = (message_index + 1) % len(last_message)
                    yield event(
                        {
                            "step": active_step,
                            "status": "running",
                            "message": last_message[message_index],
                        }
                    )
                    continue

                if kind == "error":
                    raise value
                if kind == "node":
                    app.logger.info(
                        "RDV workflow node started (request_id=%s, node=%s)",
                        request_id,
                        value,
                    )
                    if value == "profile":
                        yield event(
                            {
                                "step": "client",
                                "status": "running",
                                "message": last_message[message_index],
                            }
                        )
                    elif value in ("write", "execute"):
                        if active_step == "client":
                            yield event({"step": "client", "status": "complete"})
                            active_step = "context"
                        yield event(
                            {
                                "step": "context",
                                "status": "running",
                                "message": last_message[message_index],
                            }
                        )
                    elif value == "summary":
                        if active_step == "context":
                            yield event({"step": "context", "status": "complete"})
                        active_step = "brief"
                        yield event(
                            {
                                "step": "brief",
                                "status": "running",
                                "message": last_message[message_index],
                            }
                        )
                    continue

                # A mocked or alternate agent may return without node updates.
                if active_step == "client":
                    yield event({"step": "client", "status": "complete"})
                    yield event({"step": "context", "status": "running"})
                    active_step = "context"
                if active_step == "context":
                    yield event({"step": "context", "status": "complete"})
                    yield event({"step": "brief", "status": "running"})
                result = {"step": "brief", "status": "complete", "report": value}
                if not value["items"]:
                    result["warning"] = (
                        "Aucun sujet étayé n'a été trouvé dans les opérations."
                    )
                    app.logger.warning(
                        "RDV workflow produced no supported topics "
                        "(request_id=%s, topic_count=%d)",
                        request_id,
                        len(value["items"]),
                    )
                yield event(result)
                break
            app.logger.info(
                "RDV workflow completed (request_id=%s, topic_count=%d, "
                "duration_seconds=%.2f)",
                request_id,
                len(value["items"]),
                time.monotonic() - started_at,
            )
            yield event({"status": "done"})
        except Exception as exc:
            app.logger.exception(
                "RDV workflow failed (request_id=%s, duration_seconds=%.2f)",
                request_id,
                time.monotonic() - started_at,
            )
            message = (
                str(exc)
                if isinstance(exc, ValueError)
                else "La préparation du rendez-vous a échoué. Réessayez."
            )
            yield event({"status": "error", "message": message})

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
