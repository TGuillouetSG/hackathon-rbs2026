"""Synthetic customer catalog and profile-backed display facts for the demo."""

import json
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_CUSTOMER_ID = "annie"


CUSTOMERS = {
    record["id"]: record
    for record in json.loads((DATA_DIR / "customers.json").read_text(encoding="utf-8"))
}


def customer_csv(customer):
    return DATA_DIR / customer["csv"]


def _date(value):
    return date.fromisoformat(value) if value else None


def _years_since(value):
    start = _date(value)
    if not start:
        return None
    today = date.today()
    return (
        today.year - start.year - ((today.month, today.day) < (start.month, start.day))
    )


def _display_date(value):
    parsed = _date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else None


def _euros(value):
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " €"


def profile_view(customer):
    """Return only facts and suggestions supported by this customer record."""
    alerts = []
    actions = []
    if customer["address_needs_update"]:
        alerts.append(("Adresse", "Adresse à mettre à jour."))
        actions.append("Confirmer l’adresse avec le client.")
    missing_contact = [
        label
        for label, key in (("téléphone", "phone"), ("e-mail", "email"))
        if not customer[key]
    ]
    if missing_contact:
        alerts.append(
            ("Coordonnées", "À renseigner : " + ", ".join(missing_contact) + ".")
        )
        actions.append(
            "Demander les coordonnées manquantes : " + ", ".join(missing_contact) + "."
        )
    if customer["undelivered_mail_risk"]:
        alerts.append(("Courrier", "Risque de pli non distribué signalé."))
        actions.append("Vérifier le risque de pli non distribué.")
    if not customer["profession"]:
        alerts.append(("Profession", "Profession non renseignée."))
        actions.append("Compléter la profession du client.")
    if customer.get("property_signal"):
        alerts.append(("Projet immobilier possible", customer["property_signal"]))
        actions.append(
            "Demander si un projet immobilier est en cours et discuter du besoin de financement."
        )
    if not customer["last_appointment"]:
        alerts.append(("Relation", "Aucun rendez-vous affiché."))

    badges = [("Client", "b-blue"), (customer["segment"], "b-purple")]
    if customer["classification"]:
        badges.append((customer["classification"], "b-navy"))
    if customer["compliance"]:
        badges.append(("Conformité - " + customer["compliance"], "b-gray"))
    if customer["risk_flag"]:
        badges.append(("⚠ Risques", "b-amber"))
    if customer["inactive_flag"]:
        badges.append(("⚠ Inactivité Eckert", "b-amber"))

    return {
        "birth_date": _display_date(customer["birth_date"]),
        "age": _years_since(customer["birth_date"]),
        "relationship_date": _display_date(customer["relationship_since"]),
        "relationship_years": _years_since(customer["relationship_since"]),
        "last_appointment": _display_date(customer["last_appointment"]),
        "savings": _euros(customer["savings_eur"]),
        "badges": badges,
        "alerts": alerts,
        "actions": actions,
    }
