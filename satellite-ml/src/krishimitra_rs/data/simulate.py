"""Physically-grounded synthetic optical + SAR generator.

Why simulate?  Real Sentinel-1/2 ingestion needs Earth Engine auth and large
downloads; a demo must still *run* and produce credible maps. This module
generates one Rabi season over a canal command area with the same structure a
real ARD cube would have, but driven by transparent agronomy so every derived
layer (crop map, stress, advisory) can be checked against a known truth.

Generative model (per pixel, per 8-day composite):

1. **Parcels** — the command area is tessellated into fields; each field is
   assigned a crop by its area fraction (contiguous, realistic geometry).
2. **Phenology** — a crop-specific double-logistic NDVI curve vs. day-of-year.
3. **Water balance** — a FAO-56 single-bucket per pixel driven by ET0, rainfall
   and *canal-limited* irrigation supply (head-to-tail gradient + under-served
   tail fields) yields a water-stress coefficient Ks (the ground-truth stress).
4. **Observed indices** — Ks depresses NDVI/NDWI (canopy water first); soil
   moisture drives SAR VV; canopy structure drives SAR VH.
5. **Bands** — reflectances (red/nir/green/swir1) are back-solved from the
   target indices so downstream code computes indices from *bands*, exactly as
   it would on real data.
6. **Clouds** — spatially-coherent optical gaps (SAR is left intact — that is
   the whole point of adding microwave data).
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
from scipy.ndimage import gaussian_filter

from ..config import Config
from .ard import DataCube

_SAT = 0.42  # near-saturation soil volumetric water (for SAR scaling)


# --------------------------------------------------------------------------- #
# Small physical helpers
# --------------------------------------------------------------------------- #
def _event_sd(doy: int, start: _dt.date, mid: _dt.date) -> float:
    """Season-day (days since season start) for a phenology day-of-year.

    A DOY alone is ambiguous across the Dec->Jan boundary and for long-duration
    crops whose sowing precedes / harvest follows the observation window. We
    resolve it to the calendar year that lands nearest the season midpoint, then
    take a plain date difference — so sugarcane sown in October reads as a small
    negative season-day (already emerged) rather than "+359".
    """
    best = None
    for yr in (start.year - 1, start.year, start.year + 1):
        try:
            dte = _dt.date(yr, 1, 1) + _dt.timedelta(days=int(doy) - 1)
        except ValueError:
            continue
        if best is None or abs((dte - mid).days) < abs((best - mid).days):
            best = dte
    return float((best - start).days)


def _double_logistic(sd, sos_sd, peak_sd, eos_sd, base, peak):
    """Green-up + senescence double-logistic NDVI as a function of season-day."""
    sos_sd = max(sos_sd, 1.0)
    peak_sd = max(peak_sd, sos_sd + 5.0)
    eos_sd = max(eos_sd, peak_sd + 5.0)
    k_up = 6.0 / max(peak_sd - sos_sd, 5.0)
    k_dn = 6.0 / max(eos_sd - peak_sd, 5.0)
    green = 1.0 / (1.0 + np.exp(-k_up * (sd - sos_sd)))
    senes = 1.0 / (1.0 + np.exp(k_dn * (sd - eos_sd)))
    shape = np.clip(green + senes - 1.0, 0.0, 1.0)
    return base + (peak - base) * shape


def _kc_stage(sd_since_emerge: np.ndarray, fao: dict) -> np.ndarray:
    """FAO-56 stage crop coefficient Kc from days since emergence (vectorised)."""
    Li, Ld, Lm, Ll = fao["L_ini"], fao["L_dev"], fao["L_mid"], fao["L_late"]
    ci, cm, ce = fao["kc_ini"], fao["kc_mid"], fao["kc_end"]
    t = np.asarray(sd_since_emerge, dtype=float)
    kc = np.full_like(t, ci)
    if Li + Ld + Lm + Ll == 0:  # fallow / bare
        return np.full_like(t, ci)
    # pre-emergence -> bare soil
    kc = np.where(t < 0, ci * 0.4, kc)
    # development ramp Kc_ini -> Kc_mid
    dev = (t >= Li) & (t < Li + Ld)
    kc = np.where(dev, ci + (cm - ci) * (t - Li) / max(Ld, 1), kc)
    # mid-season plateau
    mid = (t >= Li + Ld) & (t < Li + Ld + Lm)
    kc = np.where(mid, cm, kc)
    # late-season ramp Kc_mid -> Kc_end
    late = (t >= Li + Ld + Lm) & (t < Li + Ld + Lm + Ll)
    kc = np.where(late, cm + (ce - cm) * (t - (Li + Ld + Lm)) / max(Ll, 1), kc)
    kc = np.where(t >= Li + Ld + Lm + Ll, ce, kc)
    return kc


def _smooth_field(rng: np.random.Generator, h: int, w: int, scale: float) -> np.ndarray:
    """Spatially-correlated random field in ~[0,1] (for supply, clouds, noise)."""
    f = gaussian_filter(rng.standard_normal((h, w)), sigma=scale)
    f -= f.min()
    if f.max() > 0:
        f /= f.max()
    return f


# --------------------------------------------------------------------------- #
# Parcels
# --------------------------------------------------------------------------- #
def _make_parcels(rng, h, w, crops):
    """Voronoi-style fields; returns (labels HxW, field_id HxW, n_fields)."""
    n_fields = max(30, (h * w) // 120)
    ys = rng.integers(0, h, n_fields)
    xs = rng.integers(0, w, n_fields)
    codes = np.array([c["code"] for c in crops])
    fr = np.array([c["fraction"] for c in crops], dtype=float)
    fr /= fr.sum()
    field_codes = rng.choice(codes, size=n_fields, p=fr)
    yy, xx = np.mgrid[0:h, 0:w]
    d = (yy[..., None] - ys[None, None, :]) ** 2 + (xx[..., None] - xs[None, None, :]) ** 2
    nearest = d.argmin(-1).astype(np.int32)
    labels = field_codes[nearest].astype(np.int16)
    return labels, nearest, n_fields, ys


# --------------------------------------------------------------------------- #
# Meteorology
# --------------------------------------------------------------------------- #
def _daily_meteorology(cfg: Config, rng):
    met = cfg.meteorology
    start, end = cfg.start_date, cfg.end_date
    D = (end - start).days + 1
    days = [start + _dt.timedelta(days=i) for i in range(D)]
    frac = np.linspace(0, 1, D)
    # ET0 lowest mid-winter, rising toward spring.
    season_shape = -np.cos(2 * np.pi * (frac * 0.5 + 0.25))
    et0 = met["et0_mm_day_mean"] + met["et0_mm_day_amp"] * season_shape
    et0 = np.clip(et0 + rng.normal(0, 0.25, D), 0.6, None)
    # Rainfall as a few western-disturbance spells.
    rain = np.zeros(D)
    n_ev = int(met["rain_events"])
    ev_days = np.sort(rng.choice(np.arange(2, D - 2), size=n_ev, replace=False))
    weights = rng.dirichlet(np.ones(n_ev))
    for dd, wgt in zip(ev_days, weights):
        span = rng.integers(1, 3)
        for k in range(span):
            if dd + k < D:
                rain[dd + k] += met["seasonal_rain_mm"] * wgt / span
    return {
        "dates_daily": [d.isoformat() for d in days],
        "et0_daily": et0.astype(np.float32).tolist(),
        "rain_daily": rain.astype(np.float32).tolist(),
        "soil": met["soil"],
    }


def _aggregate_to_composites(met, cfg: Config):
    """Sum/mean daily met into the T composite windows."""
    days = [_dt.date.fromisoformat(s) for s in met["dates_daily"]]
    et0 = np.array(met["et0_daily"])
    rain = np.array(met["rain_daily"])
    et0_c, rain_c = [], []
    for centre in cfg.composite_dates:
        lo = centre
        hi = centre + _dt.timedelta(days=cfg.composite_days)
        idx = [i for i, d in enumerate(days) if lo <= d < hi]
        if not idx:
            idx = [min(range(len(days)), key=lambda i: abs((days[i] - centre).days))]
        et0_c.append(float(et0[idx].mean()) * cfg.composite_days)  # mm over window
        rain_c.append(float(rain[idx].sum()))
    return np.array(et0_c), np.array(rain_c)


def _effective_rain(p_mm: np.ndarray) -> np.ndarray:
    """USDA-SCS effective rainfall (per composite depth)."""
    p = np.clip(p_mm, 0, None)
    eff = np.where(p < 250, p * (125 - 0.2 * p) / 125.0, 125 + 0.1 * p)
    return np.clip(eff, 0, p)


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def simulate_cube(cfg: Config) -> DataCube:
    rng = np.random.default_rng(cfg.seed)
    H, W = cfg.grid_hw
    T = cfg.n_timesteps
    # Season-day axis: plain day offsets from season start for each composite.
    sd_axis = np.array([(d - cfg.start_date).days for d in cfg.composite_dates], dtype=float)
    season_mid = cfg.start_date + _dt.timedelta(days=(cfg.end_date - cfg.start_date).days // 2)

    labels, field_id, n_fields, field_rows = _make_parcels(rng, H, W, cfg.crops)

    # ---- per-crop lookup arrays (H,W) --------------------------------------
    soil = cfg.meteorology["soil"]
    fc, wp = soil["field_capacity"], soil["wilting_point"]
    taw_per_m = soil["total_available_water_mm_m"]

    ndvi_pot = np.zeros((T, H, W), dtype=np.float32)   # unstressed potential NDVI
    kc_ts = np.zeros((T, H, W), dtype=np.float32)
    root_depth = np.zeros((H, W), dtype=np.float32)
    depl_p = np.zeros((H, W), dtype=np.float32)
    vh_peak = np.zeros((H, W), dtype=np.float32)
    vv_peak = np.zeros((H, W), dtype=np.float32)
    ndvi_peak_map = np.zeros((H, W), dtype=np.float32)

    # Precompute each crop's nominal season-day phenology once.
    crop_ph = {}
    for c in cfg.crops:
        code = int(c["code"])
        ph = c["phenology"]
        crop_ph[code] = dict(
            sos=_event_sd(ph["sos_doy"], cfg.start_date, season_mid) if ph["sos_doy"] else 0.0,
            peak=_event_sd(ph["peak_doy"], cfg.start_date, season_mid) if ph["peak_doy"] else 0.0,
            eos=_event_sd(ph["eos_doy"], cfg.start_date, season_mid) if ph["eos_doy"] else 0.0,
        )

    # Generate signatures FIELD-by-field with per-field jitter (sowing date,
    # vigour, canopy structure). This within-crop spread is what produces the
    # realistic cross-crop confusion a credible accuracy figure needs.
    for fid in range(n_fields):
        m = field_id == fid
        if not m.any():
            continue
        code = int(labels[m][0])
        c = cfg.crop_by_code(code)
        ph, fao, sar = c["phenology"], c["fao56"], c["sar"]
        idx = np.where(m)
        npix = int(m.sum())
        if code == 0:  # fallow: flat low NDVI, small field-level offset
            base_level = ph["ndvi_peak"] + rng.normal(0, 0.02)
            curve = np.full(T, base_level, dtype=float)
            kc_curve = np.full(T, fao["kc_ini"], dtype=float)
        else:
            p = crop_ph[code]
            sos_f = p["sos"] + rng.normal(0, 5.0)       # +-5 day sowing spread
            peak_f = p["peak"] + rng.normal(0, 6.0)
            eos_f = p["eos"] + rng.normal(0, 6.0)
            amp_f = ph["ndvi_peak"] * (1 + rng.normal(0, 0.07))
            base_f = ph["ndvi_base"] * (1 + rng.normal(0, 0.10))
            curve = _double_logistic(sd_axis, sos_f, peak_f, eos_f, base_f, amp_f)
            kc_curve = _kc_stage(sd_axis - sos_f, fao)
        pix_jit = 1.0 + rng.normal(0, 0.03, npix)       # per-pixel micro-variation
        for t in range(T):
            ndvi_pot[t][idx] = np.clip(curve[t] * pix_jit, 0.03, 0.95)
            kc_ts[t][idx] = kc_curve[t]
        root_depth[idx] = fao["root_depth_m"]
        depl_p[idx] = fao["depletion_p"]
        vh_peak[idx] = sar["vh_peak_db"] + rng.normal(0, 1.2)   # field structure spread
        vv_peak[idx] = sar["vv_peak_db"] + rng.normal(0, 1.0)
        ndvi_peak_map[idx] = ph["ndvi_peak"]

    # ---- canal-limited irrigation supply -----------------------------------
    # Head-to-tail gradient (top rows = canal head, well supplied) + per-field
    # deficiency; a subset of tail fields is deliberately water-short so stress
    # emerges at peak-ETc (flowering) — the scenario the advisory must catch.
    head_tail = 1.0 - 0.55 * (np.arange(H) / H)[:, None] * np.ones((1, W))  # tail -> 0.45
    field_supply = 0.62 + 0.38 * rng.random(n_fields)                       # 0.62..1.0
    short_fields = rng.choice(n_fields, size=max(6, n_fields // 4), replace=False)
    field_supply[short_fields] *= 0.40                                      # chronically short
    supply_map = head_tail * field_supply[field_id]
    supply_map = np.clip(supply_map * (0.9 + 0.2 * _smooth_field(rng, H, W, 6)), 0.15, 1.05)

    met = _daily_meteorology(cfg, rng)
    et0_c, rain_c = _aggregate_to_composites(met, cfg)
    eff_rain_c = _effective_rain(rain_c)

    # ---- FAO-56 single-bucket water balance (vectorised over pixels) -------
    taw = taw_per_m * np.maximum(root_depth, 0.2)          # (H,W) mm
    raw = np.clip(depl_p, 0.2, 0.8) * taw
    Dr = 0.30 * taw                                        # start moderately moist
    ks = np.ones((T, H, W), dtype=np.float32)
    sm_frac = np.zeros((T, H, W), dtype=np.float32)
    # seasonal canal roster: supply dips during 2 "closure" windows
    closures = np.ones(T)
    for c0 in rng.choice(np.arange(2, T - 2), size=2, replace=False):
        closures[c0:c0 + 2] = 0.35
    for t in range(T):
        etc = kc_ts[t] * et0_c[t]
        Dr = Dr + etc - eff_rain_c[t]
        Dr = np.clip(Dr, 0.0, taw)
        need = np.maximum(Dr - 0.5 * raw, 0.0)
        irr = need * supply_map * closures[t]
        Dr = np.clip(Dr - irr, 0.0, taw)
        k = np.where(Dr <= raw, 1.0, (taw - Dr) / np.maximum(taw - raw, 1e-3))
        ks[t] = np.clip(k, 0.0, 1.0)
        sm_frac[t] = fc - (Dr / np.maximum(taw, 1e-3)) * (fc - wp)
    ks[:, labels == 0] = 1.0  # fallow: no crop -> no crop stress semantics

    # temporal smoothing (canopy lags soil dry-down)
    ks_s = ks.copy()
    for t in range(1, T):
        ks_s[t] = 0.5 * ks_s[t] + 0.5 * ks_s[t - 1]

    # ---- observed indices --------------------------------------------------
    ndvi_obs = ndvi_pot * (0.55 + 0.45 * ks_s)
    ndvi_obs += rng.normal(0, cfg.data["noise"]["optical_sigma"], ndvi_obs.shape)
    ndvi_obs = np.clip(ndvi_obs, 0.02, 0.97).astype(np.float32)
    # canopy water (NDWI/NDMI) is more sensitive to stress than greenness
    ndwi_obs = (0.10 + 0.55 * ndvi_pot) * (0.35 + 0.65 * ks_s)
    ndwi_obs += rng.normal(0, cfg.data["noise"]["optical_sigma"], ndwi_obs.shape)
    ndwi_obs = np.clip(ndwi_obs, -0.2, 0.8).astype(np.float32)

    # ---- back-solve reflectance bands from indices -------------------------
    nir = 0.12 + 0.42 * ndvi_obs
    red = nir * (1.0 - ndvi_obs) / (1.0 + ndvi_obs)
    green = red * 1.15 + 0.02
    swir1 = nir * (1.0 - ndwi_obs) / (1.0 + ndwi_obs)
    for arr in (nir, red, green, swir1):
        arr += rng.normal(0, cfg.data["noise"]["optical_sigma"] * 0.5, arr.shape)
    optical = {
        "red": np.clip(red, 0.01, 0.6).astype(np.float32),
        "nir": np.clip(nir, 0.02, 0.7).astype(np.float32),
        "green": np.clip(green, 0.01, 0.6).astype(np.float32),
        "swir1": np.clip(swir1, 0.01, 0.6).astype(np.float32),
    }

    # ---- SAR backscatter (all-weather) -------------------------------------
    veg = np.clip(ndvi_pot / np.maximum(ndvi_peak_map[None], 0.2), 0, 1)
    sm_norm = np.clip((sm_frac - wp) / max(_SAT - wp, 1e-3), 0, 1)
    speckle = cfg.data["sar_speckle_db"]
    vh = -19.0 + (vh_peak[None] + 19.0) * veg
    vh += rng.normal(0, speckle, vh.shape)
    vv = -14.0 + 5.5 * sm_norm + 0.6 * (vv_peak[None] + 14.0 - 5.5) * veg
    vv += rng.normal(0, speckle, vv.shape)
    sar = {"vv": vv.astype(np.float32), "vh": vh.astype(np.float32)}

    # ---- clouds on optical only (SAR untouched) ----------------------------
    cloud_mask = np.zeros((T, H, W), dtype=bool)
    cf = float(cfg.data["cloud_fraction"])
    for t in range(T):
        field = _smooth_field(rng, H, W, 8)
        thresh = np.quantile(field, 1.0 - cf * (0.6 + 0.8 * rng.random()))
        cloud_mask[t] = field > thresh
    for b in optical:
        optical[b][cloud_mask] = np.nan

    meta = {
        "pilot": cfg.pilot["name"],
        "crop_names": cfg.code_to_name,
        "crop_colors": cfg.code_to_color,
        "pixel_size_m": cfg.pilot["pixel_size_m"],
        "source": "simulate",
        "n_fields": int(n_fields),
    }
    cube = DataCube(
        dates=cfg.composite_dates,
        optical=optical,
        sar=sar,
        cloud_mask=cloud_mask,
        met=met,
        labels=labels,
        soil_moisture=sm_frac.astype(np.float32),
        meta=meta,
        extra={
            "true_ks": ks_s.astype(np.float32),          # ground-truth stress coeff
            "ndvi_potential": ndvi_pot.astype(np.float32),
            "supply_map": supply_map.astype(np.float32),
            "field_id": field_id.astype(np.int32),
            "et0_composite": et0_c.astype(np.float32),
            "rain_composite": rain_c.astype(np.float32),
        },
    )
    return cube
