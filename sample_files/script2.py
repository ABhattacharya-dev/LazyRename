"""Summarize a monthly expense CSV by category without changing the source file."""

import csv
from collections import defaultdict


def totals_by_category(csv_path):
    totals = defaultdict(float)
    with open(csv_path, newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            totals[row["category"]] += float(row["amount"])
    return dict(totals)
