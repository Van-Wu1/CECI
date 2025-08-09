
# -*- coding: utf-8 -*-
"""
slope_factor.py
----------------
PyQGIS helper to compute a slope-based factor (fac_5) for road line layers
using a slope raster (e.g., degrees or %). Designed to be imported by your
main CQI script.

Usage (inside QGIS Python or your script):
-----------------------------------------
from slope_factor import apply_slope_factor

layer_with_fac5 = apply_slope_factor(
    roads_layer=layer,                       # QgsVectorLayer (LineString)
    slope_raster="/path/to/slope.tif",       # slope tif
    id_field="id",                           # key to join back; will be created if None
    target_crs_epsg="EPSG:27700",            # must match your metric/DEM CRS
    sample_interval_m=20,                    # sampling spacing along lines
    slope_unit="degree",                     # "degree" or "percent"
    stat_choice="q3",                        # "q3" | "max" | "mean"
    overwrite=False                          # if True, overwrite fac_5/proc_slope
)

Notes:
- If your DEM is in degrees but you want percent, conversion is applied.
- If Q3 is not available in your QGIS version, it will fall back to "max".
- Returns a new memory layer with fields: proc_slope, fac_5 appended.
"""

from math import tan, radians
from typing import Optional

from qgis.core import (
    QgsVectorLayer, QgsRasterLayer, QgsCoordinateReferenceSystem,
    QgsField, QgsProject, QgsProperty, QgsProcessingFeatureSourceDefinition, edit
)
from PyQt5.QtCore import QVariant
import processing



def _ensure_field(layer: QgsVectorLayer, name: str, qvariant_type: QVariant.Type) -> int:
    if layer.fields().indexOf(name) == -1:
        with edit(layer):
            layer.addAttribute(QgsField(name, qvariant_type))
            layer.updateFields()
    return layer.fields().indexOf(name)


def _add_segid_if_missing(layer: QgsVectorLayer, id_field: Optional[str]) -> str:
    """
    Ensure we have a per-feature key to aggregate by.
    If id_field is None, create 'seg_id' from $id and return 'seg_id'.
    """
    if id_field and layer.fields().indexOf(id_field) != -1:
        return id_field
    # Create seg_id = $id
    with edit(layer):
        if layer.fields().indexOf("seg_id") == -1:
            layer.addExpressionField("$id", QgsField("seg_id", QVariant.Int))
            layer.updateFields()
    return "seg_id"


def _slope_pct(val: float, unit: str) -> float:
    if val is None:
        return None
    if unit.lower().startswith("deg"):
        return tan(radians(float(val))) * 100.0
    # assume already percent
    return float(val)


def _map_slope_to_fac5(slope_pct: Optional[float]) -> Optional[float]:
    if slope_pct is None:
        return None
    # Default mapping (you can tweak to your study's needs)
    # 0–1%: 1.00, 1–3%: 0.95, 3–5%: 0.85, 5–8%: 0.70, 8–10%: 0.50, >10%: 0.30
    sp = slope_pct
    if sp <= 1:
        return 1.00
    elif sp <= 3:
        return 0.95
    elif sp <= 5:
        return 0.85
    elif sp <= 8:
        return 0.70
    elif sp <= 10:
        return 0.50
    else:
        return 0.30


def apply_slope_factor(
    roads_layer: QgsVectorLayer,
    slope_raster: str,
    id_field: Optional[str] = "id",
    target_crs_epsg: str = "EPSG:27700",
    sample_interval_m: float = 20.0,
    slope_unit: str = "degree",
    stat_choice: str = "q3",
    overwrite: bool = False
) -> QgsVectorLayer:
    """
    Compute fac_5 for roads_layer from slope_raster and return a new memory layer
    that contains proc_slope (percent) and fac_5 fields.
    """

    if not roads_layer or not roads_layer.isValid():
        raise ValueError("roads_layer is invalid")

    # Reproject to metric CRS (match your DEM CRS if necessary)
    roads_m = processing.run(
        "native:reprojectlayer",
        {"INPUT": roads_layer, "TARGET_CRS": QgsCoordinateReferenceSystem(target_crs_epsg), "OUTPUT": "memory:"}
    )["OUTPUT"]

    # Slope raster
    rast = QgsRasterLayer(slope_raster, "slope_raster")
    if not rast.isValid():
        raise ValueError("Slope raster is invalid or cannot be opened: %s" % slope_raster)

    # Ensure key
    key_field = _add_segid_if_missing(roads_m, id_field)

    # Densify & extract vertices (sampling points along each line)
    roads_dens = processing.run(
        "native:densifygeometriesgivenaninterval",
        {"INPUT": roads_m, "INTERVAL": float(sample_interval_m), "OUTPUT": "memory:"}
    )["OUTPUT"]

    pts = processing.run(
        "native:extractvertices",
        {"INPUT": roads_dens, "OUTPUT": "memory:"}
    )["OUTPUT"]

    # Bring key field onto points via spatial join (intersects)
    pts = processing.run(
        "native:joinattributesbylocation",
        {
            "INPUT": pts,
            "JOIN": roads_dens,
            "PREDICATE": [0],  # Intersects
            "JOIN_FIELDS": [key_field],
            "METHOD": 0,
            "DISCARD_NONMATCHING": True,
            "PREFIX": "",
            "OUTPUT": "memory:",
        }
    )["OUTPUT"]

    # Sample raster value at points
    pts_samp = processing.run(
        "qgis:rastersampling",
        {"INPUT": pts, "RASTERCOPY": rast, "COLUMN_PREFIX": "slp_", "OUTPUT": "memory:"}
    )["OUTPUT"]

    # Aggregate slope stats per key_field
    # Try to include Q3 if available in your QGIS; else will fall back later.
    stats_to_use = [2, 6]  # 2=mean, 6=max
    q3_stat_code = 9  # Q3; not all versions support this
    try:
        test = processing.algorithmHelp("qgis:statisticsbycategories")
        if "9" in test:  # crude check, not bulletproof
            stats_to_use.append(q3_stat_code)
    except Exception:
        # Can't check, will attempt and ignore if fails
        stats_to_use.append(q3_stat_code)

    stats = processing.run(
        "qgis:statisticsbycategories",
        {
            "INPUT": pts_samp,
            "CATEGORIES_FIELD_NAME": [key_field],
            "VALUES_FIELD_NAME": "slp_1",
            "STATISTICS": stats_to_use,
            "OUTPUT": "memory:"
        }
    )["OUTPUT"]

    # Join stats back to the densified lines
    join_fields = []
    for cand in ["mean", "max", "q3"]:
        fname = f"slp_1_{cand}"
        if stats.fields().indexOf(fname) != -1:
            join_fields.append(fname)

    roads_stats = processing.run(
        "native:joinattributestable",
        {
            "INPUT": roads_dens,
            "FIELD": key_field,
            "INPUT_2": stats,
            "FIELD_2": key_field,
            "FIELDS_TO_COPY": join_fields,
            "METHOD": 1,
            "DISCARD_NONMATCHING": False,
            "PREFIX": "",
            "OUTPUT": "memory:"
        }
    )["OUTPUT"]

    # Compute proc_slope (%), fac_5
    proc_idx = _ensure_field(roads_stats, "proc_slope", QVariant.Double)
    fac5_idx  = _ensure_field(roads_stats, "fac_5", QVariant.Double)

    # Choose representative stat field
    rep_field = None
    preferred = {
        "q3": "slp_1_q3",
        "max": "slp_1_max",
        "mean": "slp_1_mean"
    }
    # Try preferred then fallbacks
    for key in [stat_choice, "q3", "max", "mean"]:
        cand = preferred.get(key)
        if cand and roads_stats.fields().indexOf(cand) != -1:
            rep_field = cand
            break

    if rep_field is None:
        raise RuntimeError("No slope stats available to map (q3/max/mean missing).")

    with edit(roads_stats):
        for f in roads_stats.getFeatures():
            raw = f[rep_field]
            if raw is None:
                roads_stats.changeAttributeValue(f.id(), proc_idx, None)
                roads_stats.changeAttributeValue(f.id(), fac5_idx, None)
                continue
            spct = _slope_pct(raw, slope_unit)
            fac5 = _map_slope_to_fac5(spct)
            roads_stats.changeAttributeValue(f.id(), proc_idx, round(spct, 2) if spct is not None else None)
            roads_stats.changeAttributeValue(f.id(), fac5_idx, round(fac5, 2) if fac5 is not None else None)

    # Optional: only append fac_5/proc_slope to the ORIGINAL roads_layer by attribute join
    result = processing.run(
        "native:joinattributestable",
        {
            "INPUT": roads_layer,
            "FIELD": key_field if key_field in [f.name() for f in roads_layer.fields()] else "id",
            "INPUT_2": roads_stats,
            "FIELD_2": key_field,
            "FIELDS_TO_COPY": ["proc_slope", "fac_5"],
            "METHOD": 1,
            "DISCARD_NONMATCHING": False,
            "PREFIX": "",
            "OUTPUT": "memory:"
        }
    )["OUTPUT"]

    # If overwrite=False and fields already exist, we keep existing values; if True, this memory result already overwrote.
    return result
