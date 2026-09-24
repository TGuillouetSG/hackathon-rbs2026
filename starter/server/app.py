
import os
import sys
import json
from pathlib import Path

from flask import Flask, Response, render_template

app = Flask(__name__, static_folder='static', static_url_path='/static')

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/rdv")
def rdv():
    return render_template('rdv.html')


@app.post("/api/rdv/workflow")
def rdv_workflow():
    """Prepare the appointment brief and report progress after each step."""
    steps = ("client", "context", "brief")
    def event_stream():
        try:
            for step in steps:
                yield f"data: {json.dumps({'step': step, 'status': 'running'}, ensure_ascii=False)}\n\n"
                if step == "brief":
                    # Use Foundry when configured; local demos get a useful fallback.
                    starter_dir = Path(__file__).resolve().parents[1]
                    if str(starter_dir) not in sys.path:
                        sys.path.insert(0, str(starter_dir))
                    try:
                        from client import FoundryClient
                        synthesis = FoundryClient().query(
                            "Tu es un assistant bancaire. Réponds en français, brièvement, avec une synthèse utile pour préparer un rendez-vous.",
                            "Prépare les points à aborder pour le rendez-vous de Mme Annie BERTOUD. "
                            "Informations client : coordonnées à mettre à jour, risque de pli non distribué, "
                            "profession non renseignée, aucun rendez-vous ni compte-rendu récent. "
                            "Donne les sujets prioritaires et les questions à poser.",
                        )
                    except (ValueError, ImportError, ModuleNotFoundError):
                        if os.getenv('AZURE_OPENAI_API_KEY'):
                            raise
                        synthesis = (
                            "Vérifier les coordonnées et le risque de pli non distribué, "
                            "compléter la situation professionnelle et recueillir les besoins de la cliente."
                        )
                payload = {"step": step, "status": "complete"}
                if step == "brief":
                    payload["result"] = synthesis
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: {\"status\": \"done\"}\n\n"
        except Exception:
            app.logger.exception("Appointment preparation workflow failed")
            yield f"data: {json.dumps({'status': 'error', 'message': 'La préparation du rendez-vous a échoué. Réessayez.'}, ensure_ascii=False)}\n\n"

    return Response(event_stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
