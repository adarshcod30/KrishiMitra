"""End-to-end and unit tests for the KrishiMitra-RS pipeline.

Uses a small grid so the whole suite runs in a few seconds while still
exercising every stage: simulate -> features -> classify -> stress -> advisory.
"""
import numpy as np
import pytest

from krishimitra_rs.advisory.irrigation import generate_advisory
from krishimitra_rs.advisory.phenology_stage import (
    detect_growth_stage, kc_from_detected_stage,
)
from krishimitra_rs.advisory.water_balance import water_balance
from krishimitra_rs.config import load_config
from krishimitra_rs.data.simulate import simulate_cube
from krishimitra_rs.features.build import build_feature_stack
from krishimitra_rs.models.crop_classifier import classify_crops
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
