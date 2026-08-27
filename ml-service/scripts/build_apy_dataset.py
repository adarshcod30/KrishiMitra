#!/usr/bin/env python3
"""Turn the DES 'Area, Production & Yield' export into a tidy long table.

The portal serves an HTML table under a .xls extension, with a three-level
header (crop -> season -> A/P/Y) and state/district carried by ``rowspan``. It
also leaks a PHP array dump of its own column layout, which is the only
reliable description of the 573 data columns - the header's colspans disagree
with the body - so that dump drives the column spec here.

Output: data/apy_long.csv.gz with one row per
(state, district, year, crop, season) and area/production/yield.

    python scripts/build_apy_dataset.py --source data/apy_raw/<file>.xls
"""
from __future__ import annotations

import argparse
import csv
import gzip
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "apy_long.csv.gz"

# Leading "12. " ordinals the portal prefixes to state and district names.
ORDINAL = re.compile(r"^\s*\d+\.\s*")
WHITESPACE = re.compile(r"\s+")


def clean_name(text: str) -> str:
    return WHITESPACE.sub(" ", ORDINAL.sub("", text or "")).strip()


def column_spec(html: str) -> list[tuple[str, str]]:
    """(crop, season) pairs in column order, from the portal's own PHP dump."""
    start = html.index("<pre>Array")
    dump = html[start : html.index("</pre>", start)]
    spec: list[tuple[str, str]] = []
    # Each crop block lists its seasons in the order its columns appear.
    for block in re.split(r"\[crop_name\] => ", dump)[1:]:
        crop = block.split("\n", 1)[0].strip()
        for season in re.findall(r"\[session_name\] => ([^\n]+)", block):
            spec.append((crop, season.strip()))
    return spec


def to_number(raw: str) -> float | None:
    text = WHITESPACE.sub("", re.sub(r"<[^>]+>", "", raw or ""))
    if not text or text in {"-", "NA", "N/A"}:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    args = ap.parse_args()

    html = args.source.read_text(encoding="utf-8", errors="replace")
    spec = column_spec(html)
    expected = len(spec) * 3
    print(f"{len(spec)} crop-season columns ({expected} data cells per row)")

    body = html[html.index("<tbody>") :]
    rows = re.finditer(r"<tr>(.*?)</tr>", body, re.S)

    state = district = ""
    written = skipped = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["state", "district", "year", "crop", "season",
             "area_ha", "production_t", "yield_t_per_ha"]
        )
        for match in rows:
            cells = re.findall(r"<td([^>]*)>(.*?)</td>", match.group(1), re.S)
            if len(cells) < expected + 1:
                skipped += 1
                continue
            # The trailing (1 + expected) cells are year + data; anything before
            # them is a rowspan'd state and/or district starting a new group.
            leading = cells[: len(cells) - expected - 1]
            # 2 leading cells start a new state (and its first district);
            # 1 starts a new district inside the current state; 0 continues both.
            names = [clean_name(re.sub(r"<[^>]+>", "", value)) for _, value in leading]
            names = [n for n in names if n]
            if len(names) >= 2:
                state, district = names[0], names[1]
            elif len(names) == 1:
                district = names[0]

            tail = cells[len(cells) - expected - 1 :]
            year = clean_name(re.sub(r"<[^>]+>", "", tail[0][1]))
            values = [to_number(v) for _, v in tail[1:]]

            for index, (crop, season) in enumerate(spec):
                area, production, yld = values[index * 3 : index * 3 + 3]
                # A crop-season with no area was not grown here; skip rather
                # than emit millions of empty rows.
                if area is None and production is None and yld is None:
                    continue
                writer.writerow([state, district, year, crop, season,
                                 area, production, yld])
                written += 1

    size = OUT.stat().st_size / 1e6
    print(f"wrote {written:,} long rows -> {OUT.name} ({size:.1f} MB)")
    if skipped:
        print(f"skipped {skipped} malformed rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
