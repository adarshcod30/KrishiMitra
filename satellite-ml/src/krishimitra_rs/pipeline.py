"""End-to-end orchestration: data -> features -> crop map -> stress -> advisory.

Run it as a module or via the ``krishimitra-rs`` console script::

    python -m krishimitra_rs.pipeline --config config/pilot_area.yaml

It produces, under ``outputs/``:
    maps/      crop_type_map.png, moisture_stress_map.png, irrigation_advisory_map.png (+GeoTIFFs)
    figures/   phenology_curves.png, timeseries_panels.png, confusion_matrix.png
    tables/    run_summary.json, validation_report.json, per_crop_area.csv
    models/    crop_classifier.joblib
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .advisory.irrigation import AdvisoryResult, generate_advisory
from .advisory.phenology_stage import detect_growth_stage, kc_from_detected_stage
from .advisory.water_balance import WaterBalanceResult, water_balance
from .config import Config, load_config
from .features.build import FeatureStack, build_feature_stack
from .models.crop_classifier import (
    ClassificationResult,
    classify_crops,
    unsupervised_crop_map,
)
from .models.stress import StressResult, detect_moisture_stress
from .validation.metrics import build_validation_report


@dataclass
class PipelineResult:
    cfg: Config
    cube: Any
    fs: FeatureStack
    crop: ClassificationResult
    stage: np.ndarray
    stress: StressResult
    kc: np.ndarray
    wb: WaterBalanceResult
    advisory: AdvisoryResult
    report: dict
    figures: dict
    timings: dict


def _log(msg: str) -> None:
    print(f"[krishimitra-rs] {msg}", flush=True)


def _attach_labels(cube, cfg: Config):
    """Attach user-supplied crop labels (``data.labels_path``) to a cube.

    Lets the GEE path do supervised crop typing: export your ground-truth plots
    to an ``(H, W)`` int grid of crop codes (``.npy`` or comma-separated
    ``.csv``, 0 = fallow/no-crop) on the config grid and point
    ``data.labels_path`` at it. Silently a no-op when the cube already carries
    labels or no path is configured.
    """
    path = cfg.data.get("labels_path")
    if not path or cube.labels is not None:
        return cube
    p = Path(path)
    if not p.is_absolute():
        p = cfg.base_dir / p
    if not p.is_file():
        _log(f"    data.labels_path -> {p} not found; continuing without labels")
        return cube
    try:
        arr = np.load(p) if p.suffix.lower() == ".npy" else np.loadtxt(p, delimiter=",")
        arr = np.asarray(arr).astype(np.int16)
    except Exception as exc:
        _log(f"    could not read data.labels_path {p}: {exc}; continuing without labels")
        return cube
    if arr.shape != (cube.H, cube.W):
        _log(f"    data.labels_path grid {arr.shape} != cube grid "
             f"{(cube.H, cube.W)}; ignoring")
        return cube
    cube.labels = arr
    _log(f"    loaded ground-truth labels from {p}")
    return cube


def get_cube(cfg: Config):
    """Fetch an ARD cube from the configured source."""
    source = cfg.data.get("source", "simulate")
    if source == "simulate":
        from .data.simulate import simulate_cube
        return _attach_labels(simulate_cube(cfg), cfg)
    if source == "gee":
        from .data.gee_ingest import ingest_gee_cube
        return _attach_labels(ingest_gee_cube(cfg), cfg)
    raise ValueError(f"Unknown data.source: {source!r}")


def run(
    config_path: str | Path | None = None,
    make_figures: bool = True,
    save_artifacts: bool = True,
    overrides: dict | None = None,
) -> PipelineResult:
    t = {}
    cfg = load_config(config_path)
    if overrides:
        for k, v in overrides.items():
            cfg.data[k] = v

    t0 = time.time()
    _log(f"1/7 Acquiring ARD cube (source={cfg.data.get('source')}) ...")
    cube = get_cube(cfg)
    t["data"] = time.time() - t0
    _log(f"    grid {cube.H}x{cube.W}, {cube.T} composites, "
         f"{cube.dates[0]} -> {cube.dates[-1]}")

    t0 = time.time()
    _log("2/7 Extracting features (indices, texture, phenology) ...")
    fs = build_feature_stack(cube)
    t["features"] = time.time() - t0
    _log(f"    {fs.n_features} features/pixel over {fs.X.shape[0]} pixels")

    t0 = time.time()
    if cube.labels is None:
        _log("3/7 SKIPPING supervised crop-type classification: this cube carries no "
             "ground-truth labels.")
        crop = unsupervised_crop_map(fs, cfg)
        nonzero = [c for c in np.unique(crop.crop_map).tolist() if c != 0]
        ref = cfg.code_to_name.get(int(nonzero[0]), "?") if nonzero else "none"
        _log(f"    -> unsupervised cropland mask instead "
             f"({100 * float((crop.crop_map != 0).mean()):.1f}% of the AOI is cropland; "
             f"FAO-56 parameters taken from the reference crop '{ref}').")
        _log("    -> indices, phenology, moisture stress and the FAO-56 advisory all "
             "still run; only crop typing (OA/kappa) is unavailable.")
        _log("    -> supply labels via data.labels_path (an (H,W) .npy/.csv of crop "
             "codes) or an Earth Engine ground-truth FeatureCollection to enable it.")
    else:
        _log("3/7 Classifying crop types (RF + XGBoost, field-disjoint validation) ...")
        crop = classify_crops(cube, fs, cfg)
        m = crop.metrics[crop.best_model]
        _log(f"    best={crop.best_model}  OA={m['overall_accuracy']:.1%}  "
             f"kappa={m['kappa']:.2f}")
    t["classify"] = time.time() - t0

    t0 = time.time()
    _log("4/7 Detecting growth stage + moisture stress ...")
    stage = detect_growth_stage(fs.indices["ndvi"], fs.pheno)
    stress = detect_moisture_stress(cube, fs, cfg, stage, crop.crop_map)
    t["stress"] = time.time() - t0
    if stress.validation:
        _log(f"    stress vs truth corr={stress.validation.get('condition_vs_trueKs_corr')}, "
             f"within-1-class agree={stress.validation.get('stress_class_within1_agree')}")

    t0 = time.time()
    _log("5/7 Reconstructing Kc + FAO-56 water balance -> irrigation advisory ...")
    kc = kc_from_detected_stage(stage, fs.pheno, crop.crop_map, cfg)
    wb = water_balance(cube, kc, fs.indices, crop.crop_map, cfg)
    advisory = generate_advisory(cube, wb, stage, crop.crop_map, cfg)
    t["advisory"] = time.time() - t0
    s = advisory.command_area_summary
    _log(f"    {s['area_needing_irrigation_ha']} ha need irrigation now/soon; "
         f"{s['total_gross_volume_ML']} ML gross demand @ {s['date']}")

    t0 = time.time()
    _log("6/7 Building validation report ...")
    report = build_validation_report(crop, stress, wb, advisory, cube, cfg)
    t["validation"] = time.time() - t0

    figures: dict = {}
    if make_figures:
        t0 = time.time()
        _log("7/7 Rendering maps and figures ...")
        from .viz.maps import render_all, save_geotiff
        bundle = PipelineResult(cfg, cube, fs, crop, stage, stress, kc, wb,
                                advisory, report, {}, t)
        figures = render_all(bundle, cfg, cfg.out_dir())
        if cfg.output.get("save_geotiff", False):
            gdir = cfg.out_dir("maps")
            save_geotiff(crop.crop_map.astype("int16"), gdir / "crop_type_map.tif", cfg)
            save_geotiff(stress.season_peak_class.astype("int16"),
                         gdir / "stress_peak.tif", cfg)
            save_geotiff(advisory.latest_class.astype("int16"),
                         gdir / "advisory_latest.tif", cfg)
        t["figures"] = time.time() - t0

    result = PipelineResult(cfg, cube, fs, crop, stage, stress, kc, wb,
                            advisory, report, figures, t)

    if save_artifacts:
        _save_artifacts(result)

    total = sum(t.values())
    _log(f"DONE in {total:.1f}s. Outputs -> {cfg.out_dir()}")
    return result


def _save_artifacts(res: PipelineResult) -> None:
    cfg = res.cfg
    tables = cfg.out_dir("tables")
    models = cfg.out_dir("models")

    # run summary
    summary = {
        "pilot": cfg.pilot["name"],
        "season": {"start": cfg.start_date.isoformat(), "end": cfg.end_date.isoformat(),
                   "composites": cfg.n_timesteps},
        "data_source": cfg.data.get("source"),
        "grid": list(cfg.grid_hw),
        "classification": res.report["classification"],
        "moisture_stress": res.report["moisture_stress"],
        "advisory": res.report["advisory"],
        "top_features": res.crop.feature_importance[:15],
        "timings_sec": {k: round(v, 2) for k, v in res.timings.items()},
        "figures": res.figures,
    }
    (tables / "run_summary.json").write_text(json.dumps(summary, indent=2))
    (tables / "validation_report.json").write_text(json.dumps(res.report, indent=2))

    # per-crop area table
    codes, counts = np.unique(res.crop.crop_map, return_counts=True)
    px_ha = (cfg.pilot["pixel_size_m"] ** 2) / 1e4
    lines = ["crop,code,pixels,area_ha,area_pct"]
    total_px = res.crop.crop_map.size
    for c, n in zip(codes.tolist(), counts.tolist()):
        name = cfg.code_to_name.get(int(c), str(c))
        lines.append(f"{name},{int(c)},{int(n)},{n * px_ha:.1f},{100 * n / total_px:.1f}")
    (tables / "per_crop_area.csv").write_text("\n".join(lines))

    # persist the deployed classifier (nothing to persist when crop typing was skipped)
    model_obj = res.crop.models.get(res.crop.best_model)
    if model_obj is None:
        _log("    (no classifier persisted: crop typing was skipped)")
        return
    try:
        import joblib
        joblib.dump({"model": model_obj, "feature_names": res.fs.names,
                     "best_model": res.crop.best_model},
                    models / "crop_classifier.joblib")
    except Exception as e:  # pragma: no cover
        _log(f"    (model not persisted: {e})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="KrishiMitra-RS end-to-end pipeline")
    ap.add_argument("--config", default=None, help="path to pilot_area.yaml")
    ap.add_argument("--source", choices=["simulate", "gee"], default=None,
                    help="override data.source")
    ap.add_argument("--no-figures", action="store_true", help="skip rendering")
    ap.add_argument("--no-save", action="store_true", help="skip writing artifacts")
    args = ap.parse_args(argv)

    cfg_path = args.config
    overrides = {}
    if args.source:
        overrides["source"] = args.source
    run(cfg_path, make_figures=not args.no_figures,
        save_artifacts=not args.no_save, overrides=overrides or None)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
