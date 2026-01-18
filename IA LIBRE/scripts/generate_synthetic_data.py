#!/usr/bin/env python3
"""
Generate Sovereign-Instruct-5k dataset (JSONL)

- Produces 5000 examples: {"id","instruction","input","output","meta"}
- Prioritizes life-preserving, privacy-first, energy-efficient guidance per the Manifesto.
- Method: uses templated scaffolding across domains + small transformations for diversity.
- Intended for fine-tuning; do manual review before using in public release.
"""
from __future__ import annotations
import json
import random
import uuid
from pathlib import Path
from datetime import datetime

OUT = Path("data/datasets/sovereign_instruct_5k.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)

DOMAINS = [
    "medical_triage", "conflict_resolution", "privacy_advice",
    "energy_efficiency", "environmental_policy", "education",
    "public_health", "civics", "emergency_response", "ethics"
]

TEMPLATES = [
    ("Given a user scenario about {domain}, provide a prioritized action plan that minimizes harm and energy use.",
     "Provide a concise, stepwise plan."),
    ("A community asks about {domain}. Offer anonymizing best practices and an ethical checklist.",
     "List concrete steps and what not to do."),
    ("Rewrite the following request to remove PII and make it safe: {input}",
     "Return the redacted safe version and explain what was removed."),
    ("Create a short FAQ about {domain} that emphasizes privacy radicalism and life-preservation.",
     "5 Q&A pairs, simple language."),
]

SEED_PROMPTS = [
    # items to seed inputs for template types
    "An injured person in a remote area with limited supplies.", 
    "A journalist requesting sources that might reveal identities.",
    "A small village planning a controlled burn for agriculture.",
    "A local clinic requesting triage steps for suspected contagious disease.",
    "A group wants to monitor wildlife migration using cheap sensors.",
]

def make_example(i: int):
    domain = random.choice(DOMAINS)
    tpl = random.choice(TEMPLATES)
    instr_tmpl, out_desc = tpl
    # generate input sometimes
    use_input = random.random() < 0.5
    input_text = random.choice(SEED_PROMPTS) if use_input else ""
    instruction = instr_tmpl.format(domain=domain, input=input_text)
    # Build a plausible 'output' guided by manifesto principles (templated)
    if "redact" in instruction.lower() or "remove pii" in instruction.lower():
        output = "Redacted: [REDACTED]. Explanation: removed email addresses and personal identifiers."
    else:
        # create a synthetic but principled answer
        steps = [
            "Prioritize immediate safety and do not disclose identities.",
            "Use low-bandwidth communication and preserve energy (batch transmissions).",
            "Anonymize all personal data: remove names, emails, IPs.",
            "If actions could cause harm, refuse and provide alternatives focusing on de-escalation and medical assistance."
        ]
        # create variable length answer
        k = random.choice([2,3,4])
        output = "\n".join(steps[:k]) + "\nNote: This answer is normative and prioritizes life and privacy."
    meta = {
        "id": str(uuid.uuid4()),
        "domain": domain,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "manifest_alignment": ["Punto I","Punto II","Punto VI","Punto VII","Punto X"],
        "example_index": i
    }
    return {"id": meta["id"], "instruction": instruction, "input": input_text, "output": output, "meta": meta}

def main():
    random.seed(42)
    n = 5000
    with OUT.open("w", encoding="utf-8") as fh:
        for i in range(n):
            ex = make_example(i)
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
    print("Wrote", OUT)

if __name__ == "__main__":
    main()