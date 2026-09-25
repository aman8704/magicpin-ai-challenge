# magicpin Vera Challenge Submission

`bot.py` is a stateful, dependency-free HTTP service implementing the five required endpoints: context ingestion, proactive ticks, replies, health and metadata. It composes concise WhatsApp messages from category, merchant, trigger and (when consent permits) customer context.

The composer is deterministic and fact-grounded: it selects supplied digest items and active offers, handles major trigger families, honors customer-facing consent/scope, uses a single CTA, and avoids invented claims. The reply router detects repeated/canned auto-replies, immediately advances explicit acceptance into action mode, backs off on timing requests, and ends on opt-out/hostility.

## Run and verify

```bash
python3 dataset/generate_dataset.py --seed-dir dataset --out dataset/expanded
python3 bot.py
# in another terminal
python3 generate_submission.py
python3 smoke_test.py
```

For the supplied evaluator, set its `BOT_URL` to `http://localhost:8080`, configure its own LLM key, then run `python3 judge_simulator.py`.

For Docker-capable hosts, deploy using the included `Dockerfile`; it starts the service on port `8080`. You will still need to configure the host's public HTTPS URL and submit that base URL in the magicpin portal. Additional useful production context would be actual conversion attribution, live calendar/inventory availability, and a verified action-execution API; this version intentionally does not claim it performed actions it cannot perform.
