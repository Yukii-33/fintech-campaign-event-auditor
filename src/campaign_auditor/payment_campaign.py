from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Literal, Mapping

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError as exc:
    if exc.name != "pydantic":
        raise

    class BaseModel:
        """Minimal construction fallback for dependency-free policy checks."""

        def __init__(self, **values: Any) -> None:
            fields = getattr(type(self), "__annotations__", {})
            missing = fields.keys() - values.keys()
            unexpected = values.keys() - fields.keys()
            if missing or unexpected:
                names = sorted(missing or unexpected)
                raise TypeError(f"invalid fields: {', '.join(names)}")
            for name, value in values.items():
                setattr(self, name, value)

    def Field(**_: Any) -> None:  # noqa: N802
        return None

from .infrai_email import InfraiEmail


class PaymentEvent(BaseModel):
    payment_event_id: str = Field(min_length=1)
    customer_email: str = Field(min_length=3, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)


class CampaignLaunch(BaseModel):
    payment: PaymentEvent
    campaign_name: str = Field(min_length=1, max_length=80)


class LaunchReceipt(BaseModel):
    payment_event_id: str
    message_id: str
    audit_note: str


class RiskDecision(BaseModel):
    action: Literal["allow_review", "manual_review", "hold"]
    reason: str
    observed_events: tuple[str, ...]
    decided_at: datetime


@dataclass(frozen=True)
class CampaignRecord:
    payment: PaymentEvent
    message_id: str


def decide_payment_action(amount: Decimal, event_names: Iterable[str]) -> RiskDecision:
    observed = tuple(sorted({name.lower() for name in event_names}))
    if "bounced" in observed:
        action, reason = "hold", "delivery bounced; verify the customer channel before acting"
    elif amount >= Decimal("10000") and "opened" not in observed:
        action, reason = "manual_review", "high-value payment notice has no observed open"
    else:
        action, reason = "allow_review", "notification evidence meets the review threshold"
    return RiskDecision(
        action=action,
        reason=reason,
        observed_events=observed,
        decided_at=datetime.now(timezone.utc),
    )


class PaymentCampaignService:
    def __init__(self, email: InfraiEmail) -> None:
        self.email = email
        self.records: dict[str, CampaignRecord] = {}

    def launch(self, request: CampaignLaunch) -> LaunchReceipt:
        payment = request.payment
        amount = f"{payment.amount:.2f} {payment.currency.upper()}"
        result = self.email.send(
            to=str(payment.customer_email),
            subject=f"{request.campaign_name}: payment notice",
            text=f"We recorded payment event {payment.payment_event_id} for {amount}.",
            idempotency_key=self._idempotency_key(payment.payment_event_id),
        )
        message_id = str(result["message_id"])
        self.records[message_id] = CampaignRecord(payment=payment, message_id=message_id)
        return LaunchReceipt(
            payment_event_id=payment.payment_event_id,
            message_id=message_id,
            audit_note="campaign notification accepted and linked to the payment event",
        )

    def review(self, message_id: str) -> RiskDecision:
        record = self.records[message_id]
        self.email.get(message_id)
        result = self.email.event_list(message_id)
        raw_events = result.get("events", [])
        names = [self._event_name(item) for item in raw_events if isinstance(item, Mapping)]
        return decide_payment_action(record.payment.amount, (name for name in names if name))

    @staticmethod
    def _event_name(event: Mapping[str, Any]) -> str:
        return str(event.get("type") or event.get("event") or "")

    @staticmethod
    def _idempotency_key(payment_event_id: str) -> str:
        digest = hashlib.sha256(payment_event_id.encode("utf-8")).hexdigest()[:24]
        return f"payment-campaign-{digest}"
