"""Assemble the end-to-end validation report.

Three layers of evidence, matching the evaluation parameters in the brief:

1. **Crop classification** — overall accuracy + Cohen's kappa on field-disjoint
   validation samples, with the >85% target flagged pass/fail.
2. **Moisture stress** — agreement of the derived stress class with the latent
   truth (simulation) and the growth-stage-awareness check.
3. **Advisory credibility** — the derived deficit must be *consistent* with the
   stress layer (more irrigation advised where the crop is more stressed). This
   is the "are the water-deficit layers credible" test the brief calls for.
"""
from __future__ import annotations

import numpy as np


def build_validation_report(cls_result, stress_result, wb, adv, cube, cfg) -> dict:
    report: dict = {}

    # --- 1. classification ---
    best = cls_result.best_model
    cls_metrics = cls_result.metrics.get(best)
    if cls_metrics is None:
        # No ground-truth labels -> supervised crop typing was skipped and an
        # unsupervised cropland mask was used. Say so instead of inventing an
        # accuracy for a model that was never trained.
        report["classification"] = {
            "best_model": best,
            "supervised": False,
            "skipped": True,
            "reason": "cube carries no ground-truth labels; supervised crop-type "
                      "classification skipped, unsupervised cropland mask used",
            "cropland_area_pct": round(float((cls_result.crop_map != 0).mean()) * 100, 1),
        }
    else:
        oa = cls_metrics["overall_accuracy"]
        report["classification"] = {
            "best_model": best,
            "supervised": True,
            "overall_accuracy": oa,
            "kappa": cls_metrics["kappa"],
            "target_oa": 0.85,
            "meets_target": bool(oa >= 0.85),
            "per_class": cls_metrics["per_class"],
            "all_models": {m: {"overall_accuracy": cls_result.metrics[m]["overall_accuracy"],
                               "kappa": cls_result.metrics[m]["kappa"]}
                           for m in cls_result.metrics},
            "n_train": int(cls_result.ground_truth.train_idx.size),
            "n_val": int(cls_result.ground_truth.val_idx.size),
        }

    # --- 2. moisture stress ---
    report["moisture_stress"] = {
        "validation": stress_result.validation,
        "growth_stage_aware": True,
        "stage_sensitivity": cfg.stress["stage_sensitivity"],
        "season_peak_stress_area_pct": {
            name: round(float((stress_result.season_peak_class == cls).mean()) * 100, 1)
            for cls, name in {0: "None", 1: "Mild", 2: "Moderate", 3: "Severe"}.items()
        },
    }

    # --- 3. advisory credibility ---
    crop_mask = cube.labels != 0 if cube.labels is not None else np.ones((cube.H, cube.W), bool)
    # correlation between recommended gross depth and observed stress condition,
    # over the whole season on cropped pixels (expect negative: drier -> more water).
    cond = stress_result.condition
    gross = adv.gross_mm
    active = stress_result.stage >= 1
    m = active & crop_mask[None]
    corr = float(np.corrcoef(gross[m].ravel(), cond[m].ravel())[0, 1]) if m.sum() > 10 else float("nan")
    credibility = {
        "advisory_vs_condition_corr": round(corr, 3),
        "interpretation": "negative correlation expected (more water advised where "
                          "canopy condition is poorer)",
        "consistent": bool(corr < -0.1),
        "latest_summary": adv.command_area_summary,
    }
    if "true_ks" in cube.extra:
        true_ks = cube.extra["true_ks"]
        corr_true = float(np.corrcoef(gross[m].ravel(), true_ks[m].ravel())[0, 1]) if m.sum() > 10 else float("nan")
        credibility["advisory_vs_trueKs_corr"] = round(corr_true, 3)
    report["advisory"] = credibility

    return report
