#!/usr/bin/env python3
"""KrishiMitra-RS interactive dashboard (Streamlit).

    pip install streamlit
    streamlit run dashboard/app.py

Runs the end-to-end pipeline (cached) and lets you scrub through the season to
watch crop growth stage, moisture stress and the irrigation advisory evolve —
the dashboard-ready output package the brief asks for.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib  # noqa: E402
import numpy as np  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import streamlit as st  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from krishimitra_rs.config import load_config  # noqa: E402
from krishimitra_rs.pipeline import run  # noqa: E402
from krishimitra_rs.viz.maps import (  # noqa: E402
    ADVISORY_COLORS, ADVISORY_LABELS, STRESS_COLORS, STRESS_LABELS,
)

st.set_page_config(page_title="KrishiMitra-RS", page_icon="🌾", layout="wide")


@st.cache_resource(show_spinner="Running satellite ML pipeline …")
def _run(seed: int, grid: int):
    cfg = load_config()
    cfg.data["seed"] = seed
    cfg.data["grid_hw"] = [grid, grid]
    return run(make_figures=False, save_artifacts=False,
               overrides={"seed": seed, "grid_hw": [grid, grid]})


def _cat_fig(arr, colors, labels, title, remap=None):
    disp = np.vectorize(lambda v: remap.get(int(v), 0))(arr) if remap else arr
    cmap = ListedColormap(colors)
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    ax.imshow(disp, cmap=cmap, norm=BoundaryNorm(np.arange(-0.5, len(colors) + 0.5), cmap.N),
              interpolation="nearest")
    ax.set_title(title, fontsize=11, fontweight="bold"); ax.set_xticks([]); ax.set_yticks([])
    ax.legend(handles=[Patch(facecolor=c, edgecolor="#333", label=l) for c, l in zip(colors, labels)],
              loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=2, frameon=False, fontsize=8)
    fig.tight_layout()
    return fig


st.title("🌾 KrishiMitra-RS — Crop Type, Moisture Stress & Irrigation Advisory")
st.caption("AI-driven analysis of optical + microwave (SAR) satellite data across crop growth stages")

with st.sidebar:
    st.header("Pilot controls")
    seed = st.number_input("Random seed", 0, 99999, 20250426, step=1)
    grid = st.select_slider("Grid size (px)", options=[80, 100, 120, 140], value=120)
    st.markdown("---")
    st.markdown("**Data source:** simulated optical+SAR\n\n"
                "Switch to real Sentinel-1/2 by setting `data.source: gee` in "
                "`config/pilot_area.yaml` and authenticating Earth Engine.")

res = _run(int(seed), int(grid))
cfg = res.cfg
rep = res.report
dates = [d.isoformat() for d in res.cube.dates]

# ---- headline metrics -----------------------------------------------------
c = rep["classification"]
adv = rep["advisory"]["latest_summary"]
m1, m2, m3, m4 = st.columns(4)
m1.metric("Crop OA", f"{c['overall_accuracy']:.1%}", f"target 85% {'✓' if c['meets_target'] else '✗'}")
m2.metric("Kappa", f"{c['kappa']:.2f}", c["best_model"])
m3.metric("Area to irrigate", f"{adv['area_needing_irrigation_ha']:.0f} ha", adv["date"])
m4.metric("Gross demand", f"{adv['total_gross_volume_ML']:.0f} ML",
          f"{adv['pct_command_area_irrigate_now']:.0f}% irrigate-now")

tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Crop map", "💧 Moisture stress",
                                  "🚰 Irrigation advisory", "📊 Validation"])

with tab1:
    col1, col2 = st.columns(2)
    _, remap, names, codes = None, {c: i for i, c in enumerate(cfg.crop_codes)}, cfg.crop_names, cfg.crop_codes
    colors = [cfg.code_to_color[c] for c in codes]
    col1.pyplot(_cat_fig(res.crop.crop_map, colors, names, "Crop-type classification", remap))
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    im = ax.imshow(res.crop.confidence, cmap="viridis", vmin=0.3, vmax=1)
    ax.set_title("Confidence", fontsize=11, fontweight="bold"); ax.set_xticks([]); ax.set_yticks([])
    fig.colorbar(im, fraction=0.046, pad=0.04); fig.tight_layout()
    col2.pyplot(fig)
    st.subheader("Per-crop accuracy")
    st.dataframe(c["per_class"])

with tab2:
    t = st.slider("Composite", 0, res.cube.T - 1, res.cube.T // 2, format="%d",
                  help="Scrub through the 8-day composites")
    st.caption(f"Date: **{dates[t]}**")
    col1, col2 = st.columns(2)
    col1.pyplot(_cat_fig(res.stress.stress_class[t], STRESS_COLORS, STRESS_LABELS,
                         f"Moisture stress — {dates[t]}"))
    col2.pyplot(_cat_fig(res.stress.season_peak_class, STRESS_COLORS, STRESS_LABELS,
                         "Season peak stress"))
    st.area_chart({k: v for k, v in res.stress.area_timeseries.items()})

with tab3:
    t2 = st.slider("Composite ", 0, res.cube.T - 1, int(res.advisory.snapshot_index), format="%d")
    st.caption(f"Date: **{dates[t2]}**  ·  headline (peak-demand) composite: "
               f"**{dates[res.advisory.snapshot_index]}**")
    col1, col2 = st.columns(2)
    col1.pyplot(_cat_fig(res.advisory.advisory_class[t2], ADVISORY_COLORS, ADVISORY_LABELS,
                         f"Irrigation advisory — {dates[t2]}"))
    fig, ax = plt.subplots(figsize=(5.2, 5.2))
    im = ax.imshow(res.advisory.gross_mm[t2], cmap="YlOrRd", vmin=0)
    ax.set_title("Gross irrigation depth (mm)", fontsize=11, fontweight="bold")
    ax.set_xticks([]); ax.set_yticks([]); fig.colorbar(im, fraction=0.046, pad=0.04)
    fig.tight_layout(); col2.pyplot(fig)
    if res.advisory.per_crop_demand:
        st.subheader("Per-crop irrigation demand (headline composite)")
        st.dataframe(res.advisory.per_crop_demand)

with tab4:
    col1, col2 = st.columns(2)
    col1.subheader("Classification"); col1.json(rep["classification"])
    col2.subheader("Moisture stress"); col2.json(rep["moisture_stress"])
    st.subheader("Advisory credibility"); st.json(rep["advisory"])
    st.subheader("Top discriminating features")
    st.dataframe({"feature": [f for f, _ in res.crop.feature_importance[:15]],
                  "importance": [round(v, 4) for _, v in res.crop.feature_importance[:15]]})
