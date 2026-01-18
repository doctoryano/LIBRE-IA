#!/usr/bin/env python3
"""
Train a small text-classification (BERT) ethics classifier.

- Purpose: classify short text as SAFE / FLAGGED (surveillance/weaponization/etc).
- Output: a HF-style model directory you can point SafetyEthicsCallback at via --ethics-model-path.

Usecase:
  python scripts/train_ethics_classifier.py --data data/ethics/train.jsonl --out models/ethics-classifier --epochs 3

Note: This is a small, reproducible example intended for operator curation of training data. For production,
use a well-curated dataset and validate heavily (red-team).
"""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from datasets import load_dataset, Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, TrainingArguments, Trainer
import numpy as np

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True, help="JSONL with {text,label} where label in {0,1}")
    p.add_argument("--out", required=True, help="output model dir")
    p.add_argument("--model", default="distilbert-base-uncased", help="backbone")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch", type=int, default=16)
    return p.parse_args()

def load_jsonl(path):
    recs = []
    with open(path, "r", encoding="utf-8") as fh:
        for ln in fh:
            recs.append(json.loads(ln))
    return recs

def main():
    args = parse_args()
    data = load_jsonl(args.data)
    ds = Dataset.from_list([{"text": r["text"], "label": int(r["label"])} for r in data])
    tokenizer = AutoTokenizer.from_pretrained(args.model, use_fast=True)
    def tok_fn(ex):
        return tokenizer(ex["text"], truncation=True, padding="max_length", max_length=256)
    tds = ds.train_test_split(test_size=0.1)
    tds = tds.map(tok_fn, batched=True)
    tds.set_format(type="torch", columns=["input_ids","attention_mask","label"])

    model = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=2)
    training_args = TrainingArguments(
        output_dir=args.out,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        num_train_epochs=args.epochs,
        logging_steps=10,
        fp16=True,
        remove_unused_columns=False
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=tds["train"], eval_dataset=tds["test"], tokenizer=tokenizer)
    trainer.train()
    trainer.save_model(args.out)
    print("Saved ethics classifier to", args.out)

if __name__ == "__main__":
    main()