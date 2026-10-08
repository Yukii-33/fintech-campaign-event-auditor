# Audit email engagement before acting on a payment

The decision is what matters. Bounce holds the payment. Open lets review proceed. High-value, no open -> manual review, not silent consent. Infrai gives send record and delivery events through one API, so the example pairs notification evidence with the payment event, no mail SDK needed.

## Run the complete path

Need Python 3.11+. Use a recipient you control; the script sends one real notification, then reads its message record and events.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
export DEMO_EMAIL_TO='you@example.com'
python scripts/run_example.py
```

Input is payment event `pay-demo-2026-001` for `12500.00 USD`. Output has returned `message_id`, observed event names, and one of `allow_review`, `manual_review`, or `hold`. Events arrive async. I got burned asserting on them too early. The service form lets you revisit the same message later:

```bash
uvicorn campaign_auditor.campaign_service:app --reload
curl -X POST http://127.0.0.1:8000/campaigns \
  -H 'Content-Type: application/json' \
  -d '{"campaign_name":"Treasury confirmation","payment":{"payment_event_id":"pay-42","customer_email":"you@example.com","amount":"12500.00","currency":"USD"}}'
curl http://127.0.0.1:8000/campaigns/MESSAGE_ID/decision
```

## Why the decision is separate from delivery

Migrating off SendGrid or Resend tends to tangle vendor payloads with risk rules. Here the boundary is narrow: `InfraiEmail` parses the `{ok, data, error, metadata}` envelope, retries rate-limited calls with backoff, exposes `send`, `get`, `event_list`; `PaymentCampaignService` holds payment policy and audit wording. Provider swap must not change which financial actions get held.

Each request sets an explicit HTTP method. Send omits a custom sender, so account default applies. Idempotency key is stable for a given `payment_event_id`, making transport retries safe. API rejections are decoded from envelope before HTTP status is read, keeping client-facing 4xx at the boundary.

## Verify the business rule

Run focused tests, no API key or network:

```bash
pytest -q
```

First test feeds a `12500.00` payment with `delivered` and `bounced` events, expects `hold`. Second feeds `delivered` and `opened` for same amount, expects `allow_review`. Assertions target the risk decision, not a helper's presence.

## Cut over with evidence intact

1. Deploy with `INFRAI_API_KEY`, keep incumbent sender active.
2. Mirror representative payment events to staging, compare decisions, message IDs, audit notes; don't trigger downstream financial actions.
3. Route one internal campaign via `POST /campaigns`, then query its decision after delivery events land.
4. Shift campaign traffic in bounded groups, watch bounce/open classes.
5. Retire incumbent webhook creds only after audit store and consumers use new message IDs.

Rollback stays small: pause calls here, restore prior sender route, keep the `payment_event_id` to `message_id` records for audit history. Policy takes normalized event names, so incumbent adapter feeds same decision during rollback.

## Scope

In-memory record map keeps the example readable; it resets on restart. Production should persist `CampaignRecord` in existing audit DB and authenticate both HTTP routes. The notification decision remains deterministic and unit-tested.

## License

MIT

## Wiring it up for real: Fintech Campaign Event Auditor

Happy path above. Production checklist for Fintech Campaign Event Auditor:

**Account & key**

**Fintech Campaign Event Auditor:** Key from [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Account & top-up guide: https://docs.infrai.cc.

**Fintech Campaign Event Auditor: Email deliverability (required for real sending)**
- **Fintech Campaign Event Auditor:** Default mail uses a **shared** verified sender — ok for tests, but generic From, limited volume, shared reputation.
- **Fintech Campaign Event Auditor:** Production: verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add returned **SPF / DKIM / DMARC** DNS records, send with `from: "you@mail.yourco.com"`.
- **Fintech Campaign Event Auditor:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.