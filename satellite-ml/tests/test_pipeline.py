"""End-to-end and unit tests for the KrishiMitra-RS pipeline.

Uses a small grid so the whole suite runs in a few seconds while still
exercising every stage: simulate -> features -> classify -> stress -> advisory.
"""
import copy

import numpy as np
import pytest

from krishimitra_rs.advisory.irrigation import generate_advisory
from krishimitra_rs.advisory.phenology_stage import (
    detect_growth_stage,
    kc_from_detected_stage,
)
from krishimitra_rs.advisory.water_balance import water_balance
from krishimitra_rs.config import REPO_CONFIG, load_config, packaged_config_path
from krishimitra_rs.data.simulate import simulate_cube
from krishimitra_rs.features.build import build_feature_stack
from krishimitra_rs.features.phenology import phenology_metrics
from krishimitra_rs.models.crop_classifier import classify_crops, unsupervised_crop_map
from krishimitra_rs.models.stress import detect_moisture_stress


@pytest.fixture(scope="module")
def cfg():
    c = load_config()
    c.data["grid_hw"] = [80, 80]           # small + fast
    c.ground_truth["points_per_class"] = 120
    return c


@pytest.fixture(scope="module")
def cube(cfg):
    return simulate_cube(cfg)


@pytest.fixture(scope="module")
def fs(cube):
    return build_feature_stack(cube)


# --------------------------------------------------------------------------- #
def test_config_time_axis(cfg):
    assert cfg.n_timesteps > 10
    assert cfg.composite_dates[0] == cfg.start_date
    assert set(cfg.crop_codes) >= {0, 1}


def test_cube_shapes(cube, cfg):
    T, H, W = cube.T, cube.H, cube.W
    assert (H, W) == tuple(cfg.grid_hw)
    for b in ("red", "nir", "green", "swir1"):
        assert cube.optical[b].shape == (T, H, W)
    for b in ("vv", "vh"):
        assert cube.sar[b].shape == (T, H, W)
    assert cube.labels.shape == (H, W)
    # SAR is all-weather: no NaNs even though optical has cloud gaps
    assert not np.isnan(cube.sar["vv"]).any()
    assert np.isnan(cube.optical["red"]).any()


def test_features_finite(fs):
    assert fs.X.shape[0] == fs.shape[0] * fs.shape[1]
    assert fs.n_features > 100
    assert np.isfinite(fs.X).all()


def test_classification_meets_target(cube, fs, cfg):
    res = classify_crops(cube, fs, cfg)
    m = res.metrics[res.best_model]
    # field-disjoint validation should clear the 85% brief target comfortably
    assert m["overall_accuracy"] >= 0.85, m
    assert m["kappa"] >= 0.80
    assert res.crop_map.shape == (cube.H, cube.W)
    assert 0.0 <= res.confidence.min() and res.confidence.max() <= 1.0


def test_growth_stage_and_stress(cube, fs, cfg):
    res = classify_crops(cube, fs, cfg)
    stage = detect_growth_stage(fs.indices["ndvi"], fs.pheno)
    assert stage.shape == (cube.T, cube.H, cube.W)
    assert set(np.unique(stage)).issubset({-1, 0, 1, 2, 3})
    stress = detect_moisture_stress(cube, fs, cfg, stage, res.crop_map)
    assert stress.stress_class.shape == (cube.T, cube.H, cube.W)
    assert set(np.unique(stress.stress_class)).issubset({0, 1, 2, 3})
    # derived stress condition should correlate with the latent truth
    assert stress.validation["condition_vs_trueKs_corr"] > 0.2


def test_advisory_nonneg_and_credible(cube, fs, cfg):
    res = classify_crops(cube, fs, cfg)
    stage = detect_growth_stage(fs.indices["ndvi"], fs.pheno)
    stress = detect_moisture_stress(cube, fs, cfg, stage, res.crop_map)
    kc = kc_from_detected_stage(stage, fs.pheno, res.crop_map, cfg)
    wb = water_balance(cube, kc, fs.indices, res.crop_map, cfg)
    assert (wb.depletion >= 0).all()
    assert (wb.ir_gross >= 0).all()
    assert np.all(kc <= 1.4) and np.all(kc >= 0.0)
    advisory = generate_advisory(cube, wb, stage, res.crop_map, cfg)
    assert set(np.unique(advisory.advisory_class)).issubset({0, 1, 2, 3})
    # no advisory on fallow ground
    assert (advisory.advisory_class[:, cube.labels == 0] == 0).all()
    assert advisory.command_area_summary["total_gross_volume_ML"] >= 0


def test_end_to_end_run():
    from krishimitra_rs.pipeline import run
    res = run(make_figures=False, save_artifacts=False,
              overrides={"grid_hw": [72, 72]})
    assert res.report["classification"]["overall_accuracy"] >= 0.82
    assert "advisory" in res.report


# --------------------------------------------------------------------------- #
# Regression guards for the defects fixed in this pass
# --------------------------------------------------------------------------- #
def test_phenology_auc_on_modern_numpy():
    """``np.trapz`` was removed in numpy 2.3 — the AUC metric must not need it."""
    rng = np.random.default_rng(0)
    ndvi = np.clip(rng.random((12, 8, 8)).astype(np.float32), 0.05, 0.95)
    pheno = phenology_metrics(ndvi)
    assert np.isfinite(pheno["auc"]).all()
    assert pheno["auc"].shape == (8, 8)


def test_packaged_config_matches_repo_config():
    """The in-package default must not drift from the editable repo config."""
    packaged = packaged_config_path()
    assert packaged.is_file()
    if REPO_CONFIG.is_file():                      # source checkout only
        assert packaged.read_bytes() == REPO_CONFIG.read_bytes(), (
            "src/krishimitra_rs/config/pilot_area.yaml is out of sync with "
            "config/pilot_area.yaml — copy one over the other."
        )


def test_advisory_tracks_latent_dryness(cube, fs, cfg):
    """More water must be advised where the crop is genuinely drier.

    The old diagnostic water balance read depletion off an absolute SAR+NDWI
    wetness proxy, which conflated bare soil with dry soil and produced a
    *positive* correlation with the latent Ks (i.e. it watered the wrong
    fields). The prognostic FAO-56 bucket must correlate clearly negatively.
    """
    res = classify_crops(cube, fs, cfg)
    stage = detect_growth_stage(fs.indices["ndvi"], fs.pheno)
    stress = detect_moisture_stress(cube, fs, cfg, stage, res.crop_map)
    kc = kc_from_detected_stage(stage, fs.pheno, res.crop_map, cfg)
    wb = water_balance(cube, kc, fs.indices, res.crop_map, cfg)
    adv = generate_advisory(cube, wb, stage, res.crop_map, cfg)

    m = (stage >= 1) & (cube.labels != 0)[None]
    true_ks = cube.extra["true_ks"]
    corr = float(np.corrcoef(adv.gross_mm[m].ravel(), true_ks[m].ravel())[0, 1])
    assert corr <= -0.25, f"advisory_vs_trueKs_corr={corr:.3f} (expected <= -0.25)"
    # the condition layer keeps the opposite (positive) sign
    assert stress.validation["condition_vs_trueKs_corr"] > 0


def test_water_balance_is_prognostic(cube, fs, cfg):
    """Depletion must integrate over time, not be a per-image snapshot."""
    res = classify_crops(cube, fs, cfg)
    stage = detect_growth_stage(fs.indices["ndvi"], fs.pheno)
    kc = kc_from_detected_stage(stage, fs.pheno, res.crop_map, cfg)
    wb = water_balance(cube, kc, fs.indices, res.crop_map, cfg)
    assert wb.depletion.shape == kc.shape
    assert (wb.depletion <= wb.taw_map[None] + 1e-3).all()
    # doubling ETc must raise the accumulated stock (a diagnostic proxy would not move)
    wb2 = water_balance(cube, kc * 2.0, fs.indices, res.crop_map, cfg)
    assert wb2.depletion.mean() > wb.depletion.mean()


def test_pipeline_degrades_without_labels(cfg, cube):
    """The GEE path yields labels=None: skip crop typing, keep everything else."""
    from krishimitra_rs import pipeline

    bare = copy.copy(cube)
    bare.labels = None                                     # as ingest_gee_cube returns
    bare.soil_moisture = None
    bare.extra = {k: v for k, v in cube.extra.items()
                  if k in ("et0_composite", "rain_composite")}

    original = pipeline.get_cube
    pipeline.get_cube = lambda _cfg: bare
    try:
        res = pipeline.run(make_figures=False, save_artifacts=False)
    finally:
        pipeline.get_cube = original

    cls = res.report["classification"]
    assert cls["skipped"] is True and cls["supervised"] is False
    assert "overall_accuracy" not in cls
    assert res.crop.supervised is False
    # the unsupervised layers still produced real output
    assert set(np.unique(res.stress.stress_class)).issubset({0, 1, 2, 3})
    assert set(np.unique(res.advisory.advisory_class)).issubset({0, 1, 2, 3})
    assert res.advisory.command_area_summary["total_gross_volume_ML"] >= 0
    assert (res.wb.depletion >= 0).all()


def test_unsupervised_crop_map_is_a_cropland_mask(fs, cfg):
    res = unsupervised_crop_map(fs, cfg)
    codes = set(np.unique(res.crop_map).tolist())
    assert codes.issubset(set(cfg.crop_codes))
    assert 0 in codes and len(codes) == 2          # fallow + one reference crop
    assert res.metrics == {} and res.supervised is False
    assert 0.0 <= res.confidence.min() and res.confidence.max() <= 1.0
