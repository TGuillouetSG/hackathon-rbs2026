"""Synthetic customer catalog and profile-backed display facts for the demo."""

from datetime import date
from pathlib import Path

from pydantic import BaseModel, TypeAdapter


class Powers(BaseModel):
    procurations: int
    representations: int


class Customer(BaseModel):
    id: str
    name: str
    grc_id: str
    birth_date: date
    birth_place: str
    civil_status: str
    segment: str
    classification: str | None
    compliance: str | None
    risk_flag: bool
    inactive_flag: bool
    phone: str | None
    email: str | None
    address: str | None
    address_needs_update: bool
    undelivered_mail_risk: bool
    profession: str | None
    tax_country: str | None
    branch: str
    adviser: str
    relationship_since: date
    bad_contract: bool
    bad_id: str | None
    security_phone_set: bool
    security_pass_validated: bool
    auth_criteria_set: int
    rgpd_collected: bool
    demat_applicable: bool
    daily_banking_contracts: int
    savings_contracts: int
    savings_eur: float
    powers: Powers
    last_appointment: date | None
    recent_calls: int
    reports: int
    property_signal: str | None = None
    csv: str
    motif: str = ""


STARTER_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = STARTER_DIR / "data"
DEFAULT_CUSTOMER_ID = "françoise"


CUSTOMERS: dict[str, Customer] = {
    customer.id: customer
    for customer in TypeAdapter(list[Customer]).validate_json(
        (DATA_DIR / "customers.json").read_bytes()
    )
}


def customer_csv(customer: Customer) -> Path:
    return STARTER_DIR / customer.csv


def _years_since(value: date | None) -> int | None:
    start = value
    if not start:
        return None
    today = date.today()
    return (
        today.year - start.year - ((today.month, today.day) < (start.month, start.day))
    )


def _display_date(value: date | None) -> str | None:
    return value.strftime("%d/%m/%Y") if value else None


def _euros(value):
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") + " €"


def profile_view(customer: Customer):
    """Return only facts and suggestions supported by this customer record."""
    alerts = []
    actions = []
    if customer.address_needs_update:
        alerts.append(("Adresse", "Adresse à mettre à jour."))
        actions.append("Confirmer l’adresse avec le client.")
    missing_contact = [
        label
        for label, value in (("téléphone", customer.phone), ("e-mail", customer.email))
        if not value
    ]
    if missing_contact:
        alerts.append(
            ("Coordonnées", "À renseigner : " + ", ".join(missing_contact) + ".")
        )
        actions.append(
            "Demander les coordonnées manquantes : " + ", ".join(missing_contact) + "."
        )
    if customer.undelivered_mail_risk:
        alerts.append(("Courrier", "Risque de pli non distribué signalé."))
        actions.append("Vérifier le risque de pli non distribué.")
    if not customer.profession:
        alerts.append(("Profession", "Profession non renseignée."))
        actions.append("Compléter la profession du client.")
    if customer.property_signal:
        alerts.append(("Projet immobilier possible", customer.property_signal))
        actions.append(
            "Demander si un projet immobilier est en cours et discuter du besoin de financement."
        )
    if not customer.last_appointment:
        alerts.append(("Relation", "Aucun rendez-vous affiché."))

    badges = [("Client", "b-blue"), (customer.segment, "b-purple")]
    if customer.classification:
        badges.append((customer.classification, "b-navy"))
    if customer.compliance:
        badges.append(("Conformité - " + customer.compliance, "b-gray"))
    if customer.risk_flag:
        badges.append(("⚠ Risques", "b-amber"))
    if customer.inactive_flag:
        badges.append(("⚠ Inactivité Eckert", "b-amber"))

    return {
        "birth_date": _display_date(customer.birth_date),
        "age": _years_since(customer.birth_date),
        "relationship_date": _display_date(customer.relationship_since),
        "relationship_years": _years_since(customer.relationship_since),
        "last_appointment": _display_date(customer.last_appointment),
        "savings": _euros(customer.savings_eur),
        "badges": badges,
        "alerts": alerts,
        "actions": actions,
    }
