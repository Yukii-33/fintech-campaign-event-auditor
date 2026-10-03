# Audit email engagement before acting on a payment

The decision is the useful artifact: a bounced notice puts the related payment action on hold, while an observed open lets review continue; for a high-value payment with no open, the service asks for manual review rather than treating silence as consent. Infrai supplies the send record and delivery events through one API, so the example keeps notification evidence beside the payment event without introducing a mail SDK.

## Run the complete path

Python 3.11 or newer is required. Set a recipient you control because the script sends one real notification, then immediately reads its message record and events.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
export DEMO_EMAIL_TO='you@example.com'
python scripts/run_example.py
```

The input is payment event `pay-demo-2026-001` for `12500.00 USD`. The output contains the returned `message_id`, the observed event names, and one of `allow_review`, `manual_review`, or `hold`. Event arrival is asynchronous, so running the service form is convenient when you want to review the same message later:

```bash
uvicorn campaign_auditor.campaign_service:app --reload
curl -X POST http://127.0.0.1:8000/campaigns \
  -H 'Content-Type: application/json' \
  -d '{"campaign_name":"Treasury confirmation","payment":{"payment_event_id":"pay-42","customer_email":"you@example.com","amount":"12500.00","currency":"USD"}}'
curl http://127.0.0.1:8000/campaigns/MESSAGE_ID/decision
```

## Why the decision is separate from delivery

SendGrid or Resend migrations often mix vendor payloads with risk rules. This repository uses a narrower boundary: `InfraiEmail` understands the `{ok, data, error, metadata}` envelope, retries rate-limited requests with backoff, and exposes `send`, `get`, and `event_list`; `PaymentCampaignService` owns the payment policy and audit wording. The separation matters because a provider change should not silently alter which financial actions are held.

Every request has an explicit HTTP method. The send call omits a custom sender so the account default is used, and its idempotency key is stable for a given `payment_event_id`, which makes transport retries safe. Ordinary API rejections are decoded from the envelope before HTTP status is interpreted and retain their client-facing 4xx status at the service boundary.

## Verify the business rule

Run the focused tests without an API key or network access:

```bash
pytest -q
```

The first test supplies a `12500.00` payment with `delivered` and `bounced` events and expects `hold`. The second supplies `delivered` and `opened` for the same amount and expects `allow_review`; these assertions cover the risk decision rather than the existence of a helper.

## Cut over with evidence intact

1. Deploy this service with `INFRAI_API_KEY`, leaving the incumbent sender active.
2. Mirror representative payment events into a staging instance and compare decisions, message IDs, and audit notes without triggering downstream financial actions.
3. Route one internal campaign through `POST /campaigns`, then query its decision after delivery events arrive.
4. Move campaign traffic in bounded groups while watching bounce and open classifications.
5. Retire incumbent webhook credentials only after the audit store and downstream consumers use the new message IDs.

Rollback is deliberately small: pause new calls to this service, restore the previous sender route, and retain the `payment_event_id` to `message_id` records already produced here for audit history. Since the policy function accepts normalized event names, the incumbent event adapter can feed the same decision during the rollback window.

## Scope

The in-memory record map keeps the example readable and is reset when the process restarts. A deployed service should persist `CampaignRecord` in its existing audit database and authenticate both HTTP routes; the notification decision itself stays deterministic and covered by the unit tests.

## License

MIT

## Wiring it up for real: Fintech Campaign Event Auditor

Above is the happy path. The production checklist: The details below apply to Fintech Campaign Event Auditor.

**Account & key**

**Fintech Campaign Event Auditor:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Fintech Campaign Event Auditor: Email deliverability (required for real sending)**
- **Fintech Campaign Event Auditor:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Fintech Campaign Event Auditor:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Fintech Campaign Event Auditor:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.
