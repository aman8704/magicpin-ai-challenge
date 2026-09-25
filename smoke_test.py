#!/usr/bin/env python3
"""End-to-end local contract check; run after `python3 bot.py` is started."""
import json
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8080"
def request(method, path, payload=None):
    raw = json.dumps(payload).encode() if payload is not None else None
    req = Request(BASE + path, data=raw, method=method, headers={"Content-Type":"application/json"})
    return json.loads(urlopen(req, timeout=5).read())

root = Path("dataset/expanded")
category = json.loads((root / "categories/dentists.json").read_text())
merchant = json.loads((root / "merchants/m_001_drmeera_dentist_delhi.json").read_text())
trigger = json.loads((root / "triggers/trg_001_research_digest_dentists.json").read_text())
for scope, context_id, payload in [("category", category["slug"], category), ("merchant", merchant["merchant_id"], merchant), ("trigger", trigger["id"], trigger)]:
    result = request("POST", "/v1/context", {"scope":scope,"context_id":context_id,"version":1,"payload":payload,"delivered_at":"2026-04-26T10:00:00Z"})
    assert result["accepted"] is True
actions = request("POST", "/v1/tick", {"now":"2026-04-26T10:30:00Z","available_triggers":[trigger["id"]]})["actions"]
assert len(actions) == 1 and actions[0]["body"] and actions[0]["template_name"]
reply = request("POST", "/v1/reply", {"conversation_id":actions[0]["conversation_id"],"merchant_id":merchant["merchant_id"],"customer_id":None,"from_role":"merchant","message":"Ok lets do it. Whats next?","received_at":"2026-04-26T10:45:00Z","turn_number":2})
assert reply["action"] == "send" and "action mode" in reply["body"]
health = request("GET", "/v1/healthz")
assert health["contexts_loaded"] == {"category":1,"merchant":1,"customer":0,"trigger":1}
print("HTTP smoke test passed: context, tick, reply and health contract verified.")
