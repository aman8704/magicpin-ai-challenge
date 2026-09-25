#!/usr/bin/env python3
"""Generate the required 30-line submission.jsonl from the supplied dataset."""
import json
from pathlib import Path
from bot import compose

root = Path(__file__).parent / "dataset" / "expanded"
cats = {p.stem: json.loads(p.read_text()) for p in (root / "categories").glob("*.json")}
merchants = {p.stem: json.loads(p.read_text()) for p in (root / "merchants").glob("*.json")}
customers = {p.stem: json.loads(p.read_text()) for p in (root / "customers").glob("*.json")}
triggers = {p.stem: json.loads(p.read_text()) for p in (root / "triggers").glob("*.json")}
pairs = json.loads((root / "test_pairs.json").read_text())["pairs"]
with open("submission.jsonl", "w") as out:
    for pair in pairs:
        merchant, trigger = merchants[pair["merchant_id"]], triggers[pair["trigger_id"]]
        customer = customers.get(pair.get("customer_id"))
        message = compose(cats[merchant["category_slug"]], merchant, trigger, customer)
        out.write(json.dumps({"test_id": pair["test_id"], **message}, ensure_ascii=False) + "\n")
print(f"Wrote {len(pairs)} deterministic messages to submission.jsonl")
