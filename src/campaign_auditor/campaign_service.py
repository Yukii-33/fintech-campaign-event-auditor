from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .infrai_email import InfraiEmail, InfraiError, InfraiTransportError
from .payment_campaign import CampaignLaunch, LaunchReceipt, PaymentCampaignService, RiskDecision

app = FastAPI(title="Fintech campaign event auditor")


def _service() -> PaymentCampaignService:
    service = getattr(app.state, "campaign_service", None)
    if service is None:
        service = PaymentCampaignService(InfraiEmail())
        app.state.campaign_service = service
    return service


@app.post("/campaigns", response_model=LaunchReceipt, status_code=201)
def launch_campaign(request: CampaignLaunch) -> LaunchReceipt:
    try:
        return _service().launch(request)
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail={"code": exc.code, "error": exc.detail}) from exc
    except InfraiTransportError as exc:
        raise HTTPException(status_code=502, detail="email transport unavailable") from exc


@app.get("/campaigns/{message_id}/decision", response_model=RiskDecision)
def review_campaign(message_id: str) -> RiskDecision:
    try:
        return _service().review(message_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="campaign message is not registered") from exc
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail={"code": exc.code, "error": exc.detail}) from exc
    except InfraiTransportError as exc:
        raise HTTPException(status_code=502, detail="email transport unavailable") from exc

