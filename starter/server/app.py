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
from pydantic import ValidationError

if __package__:
    from .profiles import (DEFAULT_CUSTOMER_ID, customer_by_id, customer_csv, customers,
                           profile_view, verified_demo_topics)
else:
    from profiles import (DEFAULT_CUSTOMER_ID, customer_by_id, customer_csv, customers,
                          profile_view, verified_demo_topics)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.logger.setLevel(logging.INFO)
STARTER_DIR = Path(__file__).resolve().parents[1]
WORKFLOW_HEARTBEAT_SECONDS = 4
RDV_OBJECTIVE = (
    "Analyse les données bancaires du CSV pour préparer un rendez-vous client. "
    "Propose jusqu'à trois sujets distincts et prioritaires à explorer, uniquement "
    "lorsqu'un signal précis existe. Exploite les catégories et libellés des opérations. "
    "Un projet immobilier ne peut être évoqué que si des opérations explicites "
    "(par exemple frais de projet immobilier ou virements à un notaire) l'étayent ; "
    "le total de tous les crédits ne suffit pas à l'établir. "
    "Pour une éventuelle multi-bancarité, cherche des virements externes répétés "
    "vers le même bénéficiaire et calcule leur nombre et montant ; présente-la "
    "comme une question à vérifier, jamais comme un fait certain. "
    "Pour chacun, donne un enseignement et le signal chiffré "
    "qui le justifie. Ne déduis rien qui ne soit pas étayé par les données."
)


@app.route("/")
def index():
    customer = _selected_customer()
    return render_template("index.html", customer=customer, view=profile_view(customer),
                           customers=customers().values())


@app.route("/rdv")
def rdv():
    customer = _selected_customer()
    return render_template("rdv.html", customer=customer, view=profile_view(customer),
                           customers=customers().values())


def _selected_customer():
    customer = customer_by_id(request.args.get("customer", DEFAULT_CUSTOMER_ID))
    if customer is None:
        abort(404)
    return customer


def _appointment_topics(customer_id=DEFAULT_CUSTOMER_ID, on_step=None):
    """Run the LangGraph CSV agent and return up to three complete report items."""
    if str(STARTER_DIR) not in sys.path:
        sys.path.insert(0, str(STARTER_DIR))
    from csv_agent import CsvAnalysisAgent
    from csv_tools import SummaryItem

    customer = customer_by_id(customer_id)
    if customer is None:
        raise ValueError("Client inconnu.")
    csv_path = customer_csv(customer)

    agent_rdv = CsvAnalysisAgent()
    try:
        report = agent_rdv.run(
            csv_path, RDV_OBJECTIVE, STARTER_DIR / "output" / "rdv" / customer_id,
            on_step=on_step
        )["report"]
    except RuntimeError as exc:
        if not str(exc).startswith("CSV analysis failed after one generation:"):
            raise
        topics = verified_demo_topics(customer)
        app.logger.warning("Using CSV-calculated demo topic fallback after generated analysis "
                           "failure (customer_id=%s, topic_count=%d): %s",
                           customer_id, len(topics), exc)
        return topics
    items = report.get("items") or []
    topics = []
    for item in items:
        try:
            topic = SummaryItem.model_validate(item)
        except ValidationError:
            continue
        topics.append(topic.model_dump())
        if len(topics) == 3:
            break
    if not topics:
        topics = verified_demo_topics(customer)
        if topics:
            app.logger.info("Using CSV-calculated demo topic fallback (customer_id=%s, "
                            "topic_count=%d)", customer_id, len(topics))
    app.logger.info("LangGraph agent returned to RDV API (raw_item_count=%d, "
                    "complete_topic_count=%d)", len(items), len(topics))
    return topics


@app.post("/api/rdv/workflow")
def rdv_workflow():
    """Stream progress and available CSV-backed appointment topics."""
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
                    topics = _appointment_topics(customer_id,
                                                 on_step=lambda node: updates.put(("node", node)))
                    updates.put(("result", topics))
                except Exception as exc:
                    updates.put(("error", exc))

            last_message = [
                "On rassemble les pièces du puzzle...",
                "Ils auraient pu optimiser leur démo quand même...",
                "Le futur ? c'est vous ! 😉😉",
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
            yield event({"step": "client", "status": "running",
                         "message": last_message[message_index]})
            threading.Thread(target=analyze, daemon=True).start()
            active_step = "client"
            while True:
                try:
                    kind, value = updates.get(timeout=WORKFLOW_HEARTBEAT_SECONDS)
                except queue.Empty:
                    message_index = (message_index + 1) % len(last_message)
                    yield event({"step": active_step, "status": "running",
                                 "message": last_message[message_index]})
                    continue

                if kind == "error":
                    raise value
                if kind == "node":
                    app.logger.info("RDV workflow node started (request_id=%s, node=%s)",
                                    request_id, value)
                    if value == "profile":
                        yield event({"step": "client", "status": "running",
                                     "message": last_message[message_index]})
                    elif value in ("write", "execute"):
                        if active_step == "client":
                            yield event({"step": "client", "status": "complete"})
                            active_step = "context"
                        yield event({"step": "context", "status": "running",
                                     "message": last_message[message_index]})
                    elif value == "summary":
                        if active_step == "context":
                            yield event({"step": "context", "status": "complete"})
                        active_step = "brief"
                        yield event({"step": "brief", "status": "running",
                                     "message": last_message[message_index]})
                    continue

                # A mocked or alternate agent may return without node updates.
                if active_step == "client":
                    yield event({"step": "client", "status": "complete"})
                    yield event({"step": "context", "status": "running"})
                    active_step = "context"
                if active_step == "context":
                    yield event({"step": "context", "status": "complete"})
                    yield event({"step": "brief", "status": "running"})
                result = {"step": "brief", "status": "complete", "topics": value}
                if not value:
                    result["warning"] = "Aucun sujet étayé n'a été trouvé dans les opérations."
                    app.logger.warning("RDV workflow produced no supported topics "
                                       "(request_id=%s, topic_count=%d)", request_id, len(value))
                yield event(result)
                break
            app.logger.info("RDV workflow completed (request_id=%s, topic_count=%d, "
                            "duration_seconds=%.2f)", request_id, len(value),
                            time.monotonic() - started_at)
            yield event({"status": "done"})
        except Exception as exc:
            app.logger.exception("RDV workflow failed (request_id=%s, duration_seconds=%.2f)",
                                 request_id, time.monotonic() - started_at)
            message = (str(exc) if isinstance(exc, ValueError) else
                       "La préparation du rendez-vous a échoué. Réessayez.")
            yield event({"status": "error", "message": message})

    return Response(event_stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
