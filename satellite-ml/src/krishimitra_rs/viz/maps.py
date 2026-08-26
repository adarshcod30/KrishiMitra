"""Rendering: colour-coded crop / stress / advisory maps and time-series plots.

Everything writes PNGs under ``outputs/`` (and GeoTIFFs when rasterio is
installed). The palettes are fixed and semantic — greens = healthy, reds =
severe stress / irrigate-now — so the maps read the same across every run.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

STRESS_COLORS = ["#2c7fb8", "#7fcdbb", "#fed976", "#f03b20"]        # None/Mild/Mod/Severe
STRESS_LABELS = ["None", "Mild", "Moderate", "Severe"]
ADVISORY_COLORS = ["#e5efe5", "#a1d99b", "#fdae6b", "#d7301f"]      # None/Monitor/Sched/Now
ADVISORY_LABELS = ["None", "Monitor", "Schedule", "Irrigate now"]


# --------------------------------------------------------------------------- #
def _crop_cmap(cfg):
    codes = cfg.crop_codes
    colors = [cfg.code_to_color[c] for c in codes]
    names = [cfg.code_to_name[c] for c in codes]
    cmap = ListedColormap(colors)
    # remap codes to 0..K-1 for display
    remap = {c: i for i, c in enumerate(codes)}
    return cmap, remap, names, codes


def _categorical(ax, arr, cmap, k, title):
    norm = BoundaryNorm(np.arange(-0.5, k + 0.5, 1), cmap.N)
    im = ax.imshow(arr, cmap=cmap, norm=norm, interpolation="nearest")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_xticks([]); ax.set_yticks([])
    return im


def _legend(ax, colors, labels):
    handles = [Patch(facecolor=c, edgecolor="#333", label=l) for c, l in zip(colors, labels)]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.03),
              ncol=min(len(labels), 4), frameon=False, fontsize=9)


# --------------------------------------------------------------------------- #
def plot_crop_map(crop_map, confidence, cfg, out: Path, dpi=130) -> Path:
    cmap, remap, names, codes = _crop_cmap(cfg)
    disp = np.vectorize(lambda v: remap.get(int(v), 0))(crop_map)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6))
    _categorical(axes[0], disp, cmap, len(codes), "Crop-type classification map")
    _legend(axes[0], [cfg.code_to_color[c] for c in codes], names)
    im = axes[1].imshow(confidence, cmap="viridis", vmin=0.3, vmax=1.0)
    axes[1].set_title("Classifier confidence (max class prob.)", fontsize=11, fontweight="bold")
    axes[1].set_xticks([]); axes[1].set_yticks([])
    fig.colorbar(im, ax=axes[1], fraction=0.046, pad=0.04)
    fig.suptitle(cfg.pilot["name"], fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out, dpi=dpi, bbox_inches="tight"); plt.close(fig)
    return out


def plot_stress_maps(stress, cube, cfg, out: Path, dpi=130) -> Path:
    cmap = ListedColormap(STRESS_COLORS)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6))
    _categorical(axes[0], stress.season_peak_class, cmap, 4, "Season peak moisture stress")
    _categorical(axes[1], stress.latest_class, cmap, 4,
                 f"Latest stress ({cube.dates[-1].isoformat()})")
    for ax in axes:
        _legend(ax, STRESS_COLORS, STRESS_LABELS)
    fig.suptitle("Phenology-aware moisture stress", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out, dpi=dpi, bbox_inches="tight"); plt.close(fig)
    return out


def plot_advisory_map(adv, wb, cube, cfg, out: Path, dpi=130) -> Path:
    cmap = ListedColormap(ADVISORY_COLORS)
    snap = adv.snapshot_index
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.6))
    _categorical(axes[0], adv.latest_class, cmap, 4,
                 f"Irrigation advisory ({cube.dates[snap].isoformat()}, peak demand)")
    _legend(axes[0], ADVISORY_COLORS, ADVISORY_LABELS)
    im = axes[1].imshow(adv.latest_gross_mm, cmap="YlOrRd", vmin=0)
    axes[1].set_title("Gross irrigation depth needed (mm)", fontsize=11, fontweight="bold")
    axes[1].set_xticks([]); axes[1].set_yticks([])
    fig.colorbar(im, ax=axes[1], fraction=0.046, pad=0.04, label="mm")
    fig.suptitle("8-day crop water deficit -> irrigation advisory", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(out, dpi=dpi, bbox_inches="tight"); plt.close(fig)
    return out


def plot_phenology_curves(cube, indices, cfg, out: Path, dpi=130, labels=None) -> Path:
    ndvi = indices["ndvi"]
    dates = [d.isoformat()[5:] for d in cube.dates]
    # Prefer ground truth; fall back to the derived crop map (GEE path has no labels).
    if labels is None:
        labels = cube.labels
    fig, ax = plt.subplots(figsize=(11, 5))
    for c in cfg.crops:
        m = labels == c["code"] if labels is not None else None
        if m is None or not m.any():
            continue
        mean = ndvi[:, m].mean(1)
        ax.plot(dates, mean, marker="o", ms=3, lw=1.8, color=c["color"], label=c["name"])
    ax.set_ylabel("NDVI"); ax.set_xlabel("Composite date (MM-DD)")
    ax.set_title("Multi-temporal NDVI phenology by crop", fontsize=12, fontweight="bold")
    ax.grid(alpha=0.3); ax.legend(ncol=3, fontsize=9)
    plt.xticks(rotation=45, ha="right", fontsize=8)
    fig.tight_layout(); fig.savefig(out, dpi=dpi, bbox_inches="tight"); plt.close(fig)
    return out


def _stacked_area(ax, dates, series_dict, colors, title, ylabel="Area fraction"):
    labels = list(series_dict.keys())
    data = np.array([series_dict[k] for k in labels])
    ax.stackplot(range(len(dates)), data, labels=labels, colors=colors, alpha=0.9)
    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels(dates, rotation=45, ha="right", fontsize=7)
    ax.set_title(title, fontsize=11, fontweight="bold"); ax.set_ylabel(ylabel)
    ax.set_ylim(0, 1); ax.legend(loc="upper left", fontsize=8, ncol=2)


def plot_timeseries_panels(stress, adv, wb, cube, out: Path, dpi=130) -> Path:
    dates = [d.isoformat()[5:] for d in cube.dates]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6))
    _stacked_area(axes[0], dates, stress.area_timeseries, STRESS_COLORS,
                  "Moisture-stress area over season")
    _stacked_area(axes[1], dates, adv.area_timeseries, ADVISORY_COLORS,
                  "Irrigation-advisory area over season")
    # Water balance: fluxes (ETc demand, effective rain) on the left axis;
    # the root-zone depletion *stock* vs the RAW threshold on the right axis.
    ax = axes[2]
    x = range(len(dates))
    ax.plot(x, wb.etc_area_series, marker="o", ms=3, color="#1b7837", label="ETc demand (mm/8d)")
    ax.bar(x, wb.peff, color="#3182bd", alpha=0.35, label="Eff. rain (mm/8d)")
    ax.set_ylabel("flux — mm / 8-day"); ax.set_ylim(0, None)
    ax2 = ax.twinx()
    ax2.plot(x, wb.depletion_area_series, marker="s", ms=3, color="#d7301f",
             label="Root-zone depletion (mm)")
    ax2.axhline(wb.raw_area_mean, ls="--", lw=1.2, color="#b30000",
                label="RAW threshold (stress)")
    ax2.set_ylabel("depletion — mm"); ax2.set_ylim(0, None)
    ax.set_xticks(list(x)); ax.set_xticklabels(dates, rotation=45, ha="right", fontsize=7)
    ax.set_title("Command-area water balance", fontsize=11, fontweight="bold")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(out, dpi=dpi, bbox_inches="tight"); plt.close(fig)
    return out


def plot_confusion_matrix(cls_metrics, out: Path, dpi=130) -> Path:
    cm = np.array(cls_metrics["confusion_matrix"], dtype=float)
    labels = cls_metrics["classes"]
    cmn = cm / np.clip(cm.sum(1, keepdims=True), 1, None)
    fig, ax = plt.subplots(figsize=(6.5, 5.6))
    im = ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels))); ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right"); ax.set_yticklabels(labels)
    ax.set_xlabel("Predicted"); ax.set_ylabel("Reference (ground truth)")
    ax.set_title(f"Confusion matrix — OA {cls_metrics['overall_accuracy']:.1%}, "
                 f"kappa {cls_metrics['kappa']:.2f}", fontsize=11, fontweight="bold")
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, f"{cmn[i, j]:.2f}", ha="center", va="center",
                    color="white" if cmn[i, j] > 0.5 else "#333", fontsize=8)
    fig.colorbar(im, fraction=0.046, pad=0.04)
    fig.tight_layout(); fig.savefig(out, dpi=dpi, bbox_inches="tight"); plt.close(fig)
    return out


def render_all(bundle, cfg, out_dir: Path) -> dict[str, str]:
    """Render the full figure set. ``bundle`` is the pipeline result namespace."""
    maps = Path(out_dir) / "maps"
    figs = Path(out_dir) / "figures"
    maps.mkdir(parents=True, exist_ok=True)
    figs.mkdir(parents=True, exist_ok=True)
    dpi = int(cfg.output.get("dpi", 130))
    paths: dict[str, str] = {}
    paths["crop_map"] = str(plot_crop_map(bundle.crop.crop_map, bundle.crop.confidence, cfg,
                                          maps / "crop_type_map.png", dpi))
    paths["stress_map"] = str(plot_stress_maps(bundle.stress, bundle.cube, cfg,
                                               maps / "moisture_stress_map.png", dpi))
    paths["advisory_map"] = str(plot_advisory_map(bundle.advisory, bundle.wb, bundle.cube, cfg,
                                                  maps / "irrigation_advisory_map.png", dpi))
    paths["phenology"] = str(plot_phenology_curves(
        bundle.cube, bundle.fs.indices, cfg, figs / "phenology_curves.png", dpi,
        labels=bundle.cube.labels if bundle.cube.labels is not None else bundle.crop.crop_map))
    paths["timeseries"] = str(plot_timeseries_panels(bundle.stress, bundle.advisory, bundle.wb,
                                                     bundle.cube, figs / "timeseries_panels.png", dpi))
    # No confusion matrix when crop typing was skipped (no ground-truth labels).
    cls_metrics = bundle.crop.metrics.get(bundle.crop.best_model)
    if cls_metrics is not None:
        paths["confusion"] = str(plot_confusion_matrix(cls_metrics,
                                                       figs / "confusion_matrix.png", dpi))
    return paths


# --------------------------------------------------------------------------- #
def save_geotiff(array: np.ndarray, path: Path, cfg) -> Path | None:
    """Write a georeferenced GeoTIFF if rasterio is available, else skip."""
    try:
        import rasterio
        from rasterio.transform import from_bounds
    except Exception:
        return None
    h, w = array.shape
    minx, miny, maxx, maxy = cfg.pilot["aoi_bbox"]
    transform = from_bounds(minx, miny, maxx, maxy, w, h)
    with rasterio.open(
        path, "w", driver="GTiff", height=h, width=w, count=1,
        dtype=str(array.dtype), crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(array, 1)
    return path
