"""Synthetic customer catalog and profile-backed display facts for the demo."""

import json
import re
import sys
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

STARTER_DIR = Path(__file__).resolve().parents[1]
if str(STARTER_DIR) not in sys.path:
    sys.path.insert(0, str(STARTER_DIR))
from utils import read_csv_rows


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_CUSTOMER_ID = "annie"


@lru_cache(maxsize=1)
def customers():
    records = json.loads((DATA_DIR / "customers.json").read_text(encoding="utf-8"))
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)) or DEFAULT_CUSTOMER_ID not in ids:
        raise ValueError("Invalid demo customer catalog")
    for record in records:
        csv_path = (DATA_DIR / record["csv"]).resolve()
        if csv_path.parent != DATA_DIR.resolve() or not csv_path.is_file():
            raise ValueError(f"Invalid CSV for demo customer {record['id']}")
    return {record["id"]: record for record in records}


def customer_by_id(customer_id):
    return customers().get(customer_id)


def customer_csv(customer):
    return DATA_DIR / customer["csv"]


def verified_demo_topics(customer):
    """Small, quantified fallback when the model returns no complete topic."""
    rows = read_csv_rows(customer_csv(customer))

    external_by_recipient = {}
    property_operations = []
    for raw_row in rows:
        # Bank exports may pad the final column name (for example "evenement ").
        row = {
            name.strip(): value for name, value in raw_row.items() if name is not None
        }
        category = row.get("categorie", "")
        label = row.get("libelle", row.get("Libellé", ""))
        detail = row.get("Détail de l'écriture", "")
        event = row.get("evenement", "")
        amount = row.get("montant_eur", row.get("Montant de l'opération", "0"))
        if (
            category == "Virement externe" and "Banque" in label
        ) or event.strip().lower() == "virement banque externe":
            # Prefer the transaction detail because bank-export labels are often generic.
            recipient = detail or label
            bank_match = re.search(r"POUR:\s*(.*?)\s+\d{2}\s+\d{2}\s+BQ\b", recipient)
            if bank_match:
                recipient = bank_match.group(1).strip()
            external_by_recipient.setdefault(recipient, []).append({"montant": amount})
        if category == "Frais projet immobilier":
            property_operations.append(row)

    topics = []
    for recipient, transfers in external_by_recipient.items():
        if len(transfers) < 3:
            continue
        total = sum((-Decimal(row["montant"]) for row in transfers), Decimal(0))
        topics.append(
            {
                "Insight": "Des virements réguliers vers une autre banque justifient de vérifier une éventuelle multi-bancarité.",
                "Signal_in_the_data": (
                    f"{len(transfers)} virements vers {recipient} totalisent {_euros(total)} "
                    "sur la période observée ; cela ne confirme pas à lui seul une autre relation bancaire."
                ),
            }
        )

    if property_operations:
        total = sum(
            (-Decimal(row["montant_eur"]) for row in property_operations), Decimal(0)
        )
        topics.append(
            {
                "Insight": "Un éventuel projet immobilier mérite d'être exploré avec le client.",
                "Signal_in_the_data": (
                    f"{len(property_operations)} opérations classées comme frais de projet immobilier "
                    f"totalisent {_euros(total)} de débits ; le projet reste à confirmer."
                ),
            }
        )
    return topics[:3]


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
