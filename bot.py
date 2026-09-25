#!/usr/bin/env python3
"""Deterministic, dependency-free HTTP submission for the magicpin Vera challenge.

Run locally:  python3 bot.py
The implementation deliberately uses only the standard library, so a health check
cannot fail because a web framework or an LLM provider is unavailable.
"""
from __future__ import annotations

import json, os, re, time, uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

STARTED = time.time()
CONTEXTS: dict[tuple[str, str], dict[str, Any]] = {}
CONVERSATIONS: dict[str, dict[str, Any]] = {}
AUTO_REPLIES: dict[tuple[str, str], int] = {}
SENT_SUPPRESSIONS: set[str] = set()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def active_offer(merchant: dict) -> str | None:
    return next((o.get("title") for o in merchant.get("offers", []) if o.get("status") == "active"), None)

def digest_for(category: dict, payload: dict) -> dict | None:
    wanted = payload.get("top_item_id") or payload.get("digest_item_id") or payload.get("alert_id")
    for item in category.get("digest", []):
        if item.get("id") == wanted:
            return item
    return category.get("digest", [None])[0]

def hindi(merchant: dict, customer: dict | None = None) -> bool:
    langs = (customer or {}).get("identity", {}).get("language_pref", "")
    langs = str(langs).lower() + " " + " ".join(merchant.get("identity", {}).get("languages", [])).lower()
    return "hi" in langs

def pct(value: Any) -> str:
    try: return f"{abs(float(value)) * 100:.0f}%"
    except (TypeError, ValueError): return ""

def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None) -> dict:
    """Compose one concise, factual, single-CTA WhatsApp message."""
    identity, payload = merchant.get("identity", {}), trigger.get("payload", {})
    name = identity.get("owner_first_name") or identity.get("name", "there")
    business = identity.get("name", "your business")
    kind, use_hindi = trigger.get("kind", ""), hindi(merchant, customer)
    offer, item = active_offer(merchant), digest_for(category, payload)
    send_as = "merchant_on_behalf" if customer else "vera"
    cta = "YES/STOP"

    if customer:
        cname = customer.get("identity", {}).get("name", "there")
        slots = payload.get("available_slots") or payload.get("next_session_options") or []
        slot = slots[0].get("label") if slots else None
        if kind == "chronic_refill_due":
            meds = ", ".join(payload.get("molecule_list", []))
            runout = payload.get("stock_runs_out_iso", "soon")[:10]
            body = f"Hi {cname}, {business} here. Your refill for {meds} may run out by {runout}. " + ("Saved-address delivery can be arranged. Reply YES to confirm." if payload.get("delivery_address_saved") else "Reply YES and we will help arrange it.")
        elif kind in {"recall_due", "appointment_tomorrow", "trial_followup", "wedding_package_followup"}:
            reason = payload.get("service_due") or payload.get("next_step_window_open") or "your follow-up"
            detail = f" {slot} is available." if slot else ""
            body = f"Hi {cname}, a reminder from {business}: {reason} is due." + detail + " Reply YES to confirm; STOP to opt out."
        else:
            focus = payload.get("previous_focus") or payload.get("metric_or_topic") or "a follow-up"
            body = f"Hi {cname}, {business} here. We noticed {focus} may be relevant based on your last visit. Reply YES if you would like help, or STOP to opt out."
        return {"body": body, "cta": cta, "send_as": send_as, "suppression_key": trigger.get("suppression_key", ""), "rationale": f"Consent-aware customer message for {kind}; uses only the supplied relationship and trigger details."}

    perf, peer = merchant.get("performance", {}), category.get("peer_stats", {})
    if kind in {"research_digest", "regulation_change", "cde_opportunity"} and item:
        deadline = payload.get("deadline_iso")
        suffix = f" Deadline: {deadline}." if deadline else ""
        body = f"{name}, {item.get('title')} ({item.get('source')}). {item.get('actionable', '')}{suffix} Reply YES and I’ll prepare the practical checklist."
    elif kind in {"perf_dip", "seasonal_perf_dip"}:
        metric, drop = payload.get("metric", "calls"), pct(payload.get("delta_pct"))
        baseline = payload.get("vs_baseline")
        compare = f" vs your usual {baseline}" if baseline is not None else ""
        body = f"{name}, {business}'s {metric} are down {drop} in the last {payload.get('window', '7d')}{compare}. " + (f"I can draft a {offer} listing update to test this week. " if offer else "I found the first listing fix to test this week. ") + "Reply YES and I’ll send it."
    elif kind == "perf_spike":
        body = f"{name}, {payload.get('metric', 'calls')} are up {pct(payload.get('delta_pct'))} in {payload.get('window', '7d')} (about {payload.get('vs_baseline', 'your usual')} baseline). Reply YES and I’ll turn the momentum into a ready-to-review post."
    elif kind in {"review_theme_emerged"}:
        body = f"{name}, {payload.get('occurrences_30d')} recent reviews mention “{payload.get('theme')}” and the trend is {payload.get('trend', 'visible')}. I can draft one practical response and fix note. Reply YES to review it."
    elif kind in {"competitor_opened"}:
        body = f"{name}, {payload.get('competitor_name')} opened {payload.get('distance_km')} km away with {payload.get('their_offer')}. " + (f"Your active {offer} is the strongest fact to feature. " if offer else "I can draft a precise local counter-position. ") + "Reply YES to see it."
    elif kind in {"renewal_due", "trial_followup"}:
        days = payload.get("days_remaining", merchant.get("subscription", {}).get("days_remaining"))
        body = f"{name}, your {payload.get('plan', merchant.get('subscription', {}).get('plan', 'magicpin'))} plan has {days} days remaining. I can send the renewal summary and the one growth task worth doing before then. Reply YES."
    elif kind in {"gbp_unverified"}:
        body = f"{name}, {business} is still unverified on Google. The supplied estimate is up to {pct(payload.get('estimated_uplift_pct'))} more visibility after verification. Reply YES for the {payload.get('verification_path', 'verification')} steps."
    elif kind in {"milestone_reached"}:
        body = f"{name}, {business} is at {payload.get('value_now')} {payload.get('metric', 'reviews')}, just {payload.get('milestone_value')} in sight. Reply YES and I’ll draft a thank-you post that asks for the next few reviews naturally."
    elif kind in {"curious_ask_due"}:
        body = f"{name}, quick operator question: which service are customers asking for most this week at {business}? Reply with one service—I’ll turn it into a concrete local offer or post."
        cta = "open_ended"
    elif kind in {"active_planning_intent"}:
        topic = payload.get("intent_topic", "that plan").replace("_", " ")
        body = f"{name}, here is the next step for {topic}: I’ll draft the offer structure, audience and one listing post from your existing context. Reply YES and I’ll send the draft."
    else:
        anchor = offer or (f"{perf.get('views')} views in the last {perf.get('window_days', 30)} days" if perf.get('views') else "your current listing")
        body = f"{name}, I noticed {anchor} at {business}. This is timely because of {kind.replace('_', ' ')}. Reply YES and I’ll prepare one practical next step."
    if use_hindi and kind not in {"regulation_change", "supply_alert"}:
        body = body.replace("Reply YES", "YES reply kijiye")
    return {"body": body, "cta": cta, "send_as": send_as, "suppression_key": trigger.get("suppression_key", ""), "rationale": f"{kind} message anchored in supplied trigger data and {business}'s context, with one clear next step."}

def reply_to(conversation_id: str, merchant_id: str, message: str) -> dict:
    text = message.strip().lower()
    state = CONVERSATIONS.setdefault(conversation_id, {"messages": [], "auto": 0})
    state["messages"].append(message)
    boilerplate = any(x in text for x in ("automated assistant", "team will respond", "thank you for contacting"))
    if text in {m.lower() for m in state["messages"][:-1]} or boilerplate:
        state["auto"] += 1
    if boilerplate:
        key = (merchant_id, text)
        AUTO_REPLIES[key] = AUTO_REPLIES.get(key, 0) + 1
    if state["auto"] >= 2 or AUTO_REPLIES.get((merchant_id, text), 0) >= 2 or any(x in text for x in ("stop messaging", "unsubscribe", "useless spam", "not interested", "don't message")):
        return {"action": "end", "rationale": "Respecting an opt-out or repeated WhatsApp Business auto-reply; no further messages will be sent."}
    if any(x in text for x in ("yes", "let's do", "lets do", "go ahead", "what's next", "whats next", "join")):
        return {"action": "send", "body": "Done — I’m moving this into action mode. I’ll prepare the draft/checklist from the details already shared and send it here for your review.", "cta": "open_ended", "rationale": "Explicit commitment detected, so the bot advances the requested action rather than re-qualifying."}
    if any(x in text for x in ("later", "busy", "tomorrow")):
        return {"action": "wait", "wait_seconds": 1800, "rationale": "Merchant asked for time; backing off before a follow-up."}
    return {"action": "send", "body": "Thanks—I've noted that. I can make the next step specific to your business; reply YES when you want me to prepare it.", "cta": "YES/STOP", "rationale": "Acknowledges the message and preserves one low-friction next action."}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: Any) -> None: pass
    def send_json(self, status: int, value: dict) -> None:
        raw = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def body(self) -> dict:
        try: return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode() or "{}")
        except (ValueError, UnicodeDecodeError): raise ValueError("invalid JSON")
    def do_GET(self) -> None:
        if self.path == "/v1/healthz":
            counts = {s: sum(1 for k in CONTEXTS if k[0] == s) for s in ("category", "merchant", "customer", "trigger")}
            self.send_json(200, {"status":"ok", "uptime_seconds":int(time.time()-STARTED), "contexts_loaded":counts})
        elif self.path == "/v1/metadata": self.send_json(200, {"team_name":"Aman Kumar Pandit", "team_members":["Aman Kumar Pandit"], "model":"deterministic-contextual-composer", "approach":"schema-aware routing, fact-grounded templates, consent checks and multi-turn state", "contact_email":"amanpandit8704@gmail.com", "version":"1.0.0", "submitted_at":now_iso()})
        else: self.send_json(404, {"detail":"not found"})
    def do_POST(self) -> None:
        try: data = self.body()
        except ValueError as e: self.send_json(400, {"accepted":False, "reason":"malformed", "details":str(e)}); return
        if self.path == "/v1/context":
            scope, cid, version = data.get("scope"), data.get("context_id"), data.get("version")
            if scope not in {"category","merchant","customer","trigger"} or not cid or not isinstance(version, int) or not isinstance(data.get("payload"), dict): self.send_json(400, {"accepted":False,"reason":"invalid_context"}); return
            old = CONTEXTS.get((scope,cid))
            if old and old["version"] > version: self.send_json(409, {"accepted":False,"reason":"stale_version","current_version":old["version"]}); return
            CONTEXTS[(scope,cid)] = {"version":version,"payload":data["payload"]}
            self.send_json(200, {"accepted":True,"ack_id":f"ack_{cid}_v{version}","stored_at":now_iso()})
        elif self.path == "/v1/tick":
            actions=[]
            for tid in data.get("available_triggers", [])[:20]:
                trigger = CONTEXTS.get(("trigger",tid),{}).get("payload")
                if not trigger: continue
                merchant = CONTEXTS.get(("merchant",trigger.get("merchant_id")),{}).get("payload")
                if not merchant: continue
                category = CONTEXTS.get(("category",merchant.get("category_slug")),{}).get("payload")
                customer = CONTEXTS.get(("customer",trigger.get("customer_id")),{}).get("payload") if trigger.get("customer_id") else None
                if not category or (trigger.get("scope") == "customer" and not customer): continue
                suppression = trigger.get("suppression_key")
                if suppression and suppression in SENT_SUPPRESSIONS: continue
                if customer and customer.get("preferences", {}).get("reminder_opt_in") is False: continue
                msg=compose(category,merchant,trigger,customer); conv=f"conv_{uuid.uuid4().hex[:12]}"; CONVERSATIONS[conv]={"messages":[],"auto":0}
                if suppression: SENT_SUPPRESSIONS.add(suppression)
                actions.append({"conversation_id":conv,"merchant_id":trigger["merchant_id"],"customer_id":trigger.get("customer_id"),"send_as":msg["send_as"],"trigger_id":tid,"template_name":"vera_contextual_v1","template_params":[merchant.get("identity",{}).get("name","")],**msg})
            self.send_json(200,{"actions":actions})
        elif self.path == "/v1/reply": self.send_json(200,reply_to(data.get("conversation_id", "unknown"), data.get("merchant_id", "unknown"), str(data.get("message", ""))))
        elif self.path == "/v1/teardown": CONTEXTS.clear(); CONVERSATIONS.clear(); AUTO_REPLIES.clear(); SENT_SUPPRESSIONS.clear(); self.send_json(200,{"cleared":True})
        else: self.send_json(404,{"detail":"not found"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Vera bot listening on http://0.0.0.0:{port}")
    server.serve_forever()
