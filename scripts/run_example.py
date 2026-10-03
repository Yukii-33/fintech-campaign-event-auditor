import json
import os
from decimal import Decimal

from campaign_auditor.infrai_email import InfraiEmail
from campaign_auditor.payment_campaign import CampaignLaunch, PaymentCampaignService, PaymentEvent


def main() -> None:
    recipient = os.environ.get("DEMO_EMAIL_TO")
    if not recipient:
        raise SystemExit("DEMO_EMAIL_TO is required")
    service = PaymentCampaignService(InfraiEmail())
    receipt = service.launch(
        CampaignLaunch(
            campaign_name="Treasury confirmation",
            payment=PaymentEvent(
                payment_event_id="pay-demo-2026-001",
                customer_email=recipient,
                amount=Decimal("12500.00"),
                currency="USD",
            ),
        )
    )
    decision = service.review(receipt.message_id)
    print(json.dumps({"receipt": receipt.model_dump(), "decision": decision.model_dump(mode="json")}, indent=2))


if __name__ == "__main__":
    main()

