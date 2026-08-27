#!/usr/bin/env python3
"""Train the leaf-photo disease classifier from downloaded image corpora.

Reads folders shaped ``<root>/<any>/<class name>/*.jpg``, extracts the features
in :mod:`agrotech_ml.services.leaf_features`, fits a classifier, and writes
``artifacts/leaf_model.joblib`` plus ``data/leaf_features.csv``.

The feature CSV is the durable artefact: it lets the model be retrained without
re-downloading gigabytes of images, and it is what gets committed. The image
corpora are transient.

    python scripts/train_leaf_model.py --root /tmp/kgimg --crop-map rice=rice ...
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agrotech_ml.services.leaf_features import FEATURE_NAMES, extract_features  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
IMAGE_EXT = {".jpg", ".jpeg", ".png"}

# Folder name -> (crop, human-readable condition). Keeps the model's labels
# aligned with the vocabulary the text diagnosis already uses.
CLASS_MAP = {
    # Mendeley rice corpus (CC0, ~1.5k images per class). Supersedes the older
    # 40-image-per-class set, which had no treatment entry for Leaf Smut and
    # scored f1 0.62; these four all resolve to library advice with Hindi text.
    "bacterialblight": ("rice", "Bacterial Leaf Blight"),
    "blast": ("rice", "Rice Blast"),
    "brownspot": ("rice", "Brown Spot"),
    "tungro": ("rice", "Rice Tungro"),
    "bacterial_blight": ("cotton", "Bacterial Blight"),
    "curl_virus": ("cotton", "Cotton Leaf Curl Virus"),
    "fussarium_wilt": ("cotton", "Fusarium Wilt"),
    "healthy": ("cotton", "Healthy"),
    "redrot": ("sugarcane", "Red Rot"),
    "mosaic": ("sugarcane", "Mosaic"),
    "rust": ("sugarcane", "Rust"),
    "yellow": ("sugarcane", "Yellow Leaf Disease"),
}


def discover(root: Path) -> list[tuple[Path, str, str]]:
    """Return (image path, crop, condition) for every recognised class folder."""
    found: list[tuple[Path, str, str]] = []
    for path in root.rglob("*"):
        if path.suffix.lower() not in IMAGE_EXT or not path.is_file():
            continue
        key = path.parent.name.strip().lower()
        mapped = CLASS_MAP.get(key)
        if mapped is None:
            continue
        crop, condition = mapped
        # 'Healthy' appears under more than one corpus; attribute it to the crop
        # whose directory tree it sits in so the label stays meaningful.
        if condition == "Healthy":
            lowered = str(path).lower()
            for candidate in ("sugarcane", "cotton", "rice"):
                if candidate in lowered:
                    crop = candidate
                    break
        found.append((path, crop, condition))
    return found


def train_from_features() -> int:
    """Rebuild the model from the committed feature CSV.

    This is the path CI and the deploy build take: the image corpora are far
    too large to keep, but the extracted features are small enough to commit,
    so the model stays reproducible without re-downloading gigabytes.
    """
    csv_path = ROOT / "data" / "leaf_features.csv"
    if not csv_path.is_file():
        print(f"missing {csv_path}", file=sys.stderr)
        return 1

    with csv_path.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], rows[1:]
    labels = np.array([f"{r[0]}|{r[1]}" for r in body])
    features = np.array([[float(v) for v in r[2:]] for r in body], dtype=np.float32)

    X_tr, X_te, y_tr, y_te = train_test_split(
        features, labels, test_size=0.2, random_state=42, stratify=labels
    )
    model = _build_model()
    model.fit(X_tr, y_tr)
    accuracy = accuracy_score(y_te, model.predict(X_te))
    print(f"rebuilt from {len(body)} feature rows; held-out accuracy {accuracy:.3f}")

    artifacts = ROOT / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "pipeline": model,
        "classes": sorted(set(labels.tolist())),
        "feature_names": header[2:],
        "accuracy": round(float(accuracy), 4),
        "n_images": len(labels),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, artifacts / "leaf_model.joblib")
    (ROOT / "data" / "leaf_model_card.json").write_text(json.dumps({
        "accuracy": round(float(accuracy), 4),
        "n_images": len(labels),
        "classes": sorted(set(labels.tolist())),
        "rebuilt_from": "data/leaf_features.csv",
    }, indent=2))
    print(f"wrote leaf_model.joblib ({(artifacts/'leaf_model.joblib').stat().st_size/1e6:.1f} MB)")
    return 0


def _build_model() -> Pipeline:
    """Bounded deliberately: unbounded (300 trees, leaf=2) scores 0.862 but
    weighs 92 MB, which does not fit beside the other models on a 512 MB
    instance. These bounds cost 2.4 points of accuracy for 75 MB."""
    return Pipeline([
        ("scale", StandardScaler()),
        ("clf", ExtraTreesClassifier(
            n_estimators=120, min_samples_leaf=5, max_depth=24,
            max_features="sqrt", class_weight="balanced",
            n_jobs=-1, random_state=42)),
    ])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, help="image corpus root (first build)")
    ap.add_argument(
        "--from-features", action="store_true",
        help="retrain from the committed data/leaf_features.csv, no images needed",
    )
    ap.add_argument("--min-per-class", type=int, default=25)
    args = ap.parse_args()

    if args.from_features:
        return train_from_features()

    if args.root is None:
        ap.error("pass --root <image dir> or --from-features")

    items = discover(args.root)
    if not items:
        print(f"No recognised class folders under {args.root}", file=sys.stderr)
        return 1

    counts = Counter(f"{crop}|{cond}" for _, crop, cond in items)
    usable = {label for label, n in counts.items() if n >= args.min_per_class}
    items = [it for it in items if f"{it[1]}|{it[2]}" in usable]
    print(f"{len(items)} images across {len(usable)} classes")

    started = time.time()
    rows, X, y = [], [], []
    for index, (path, crop, condition) in enumerate(items, 1):
        try:
            features = extract_features(path)
        except Exception as exc:  # corrupt files exist in public corpora
            print(f"  skipped {path.name}: {exc}")
            continue
        label = f"{crop}|{condition}"
        X.append(features)
        y.append(label)
        rows.append([crop, condition, *(round(float(v), 6) for v in features)])
        if index % 500 == 0:
            print(f"  {index}/{len(items)} ({time.time()-started:.0f}s)")

    X_arr, y_arr = np.vstack(X), np.array(y)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X_arr, y_arr, test_size=0.2, random_state=42, stratify=y_arr
    )
    model = _build_model()
    model.fit(X_tr, y_tr)
    predicted = model.predict(X_te)
    accuracy = accuracy_score(y_te, predicted)
    print(f"\nheld-out accuracy: {accuracy:.3f}  ({len(y_te)} test images)")
    print(classification_report(y_te, predicted, zero_division=0))

    features_csv = ROOT / "data" / "leaf_features.csv"
    with features_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["crop", "condition", *FEATURE_NAMES])
        writer.writerows(rows)

    artifacts = ROOT / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "pipeline": model,
        "classes": sorted(set(y_arr.tolist())),
        "feature_names": FEATURE_NAMES,
        "accuracy": round(float(accuracy), 4),
        "n_images": len(y_arr),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, artifacts / "leaf_model.joblib")

    meta = {
        "accuracy": round(float(accuracy), 4),
        "n_images": len(y_arr),
        "classes": sorted(set(y_arr.tolist())),
    }
    (ROOT / "data" / "leaf_model_card.json").write_text(json.dumps(meta, indent=2))
    print(f"\nwrote {features_csv.name}, leaf_model.joblib "
          f"({(artifacts/'leaf_model.joblib').stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
