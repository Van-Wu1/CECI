#!/usr/bin/env python3
"""
Cycling Quality Index and Offset Line Generation in pure Python (GeoPandas, Shapely).
Usage:
  python cycling_quality_index_pure_python.py [--input PATH] [--output PATH] [--offset_distance DISTANCE]
"""

import os
import glob
import argparse
import re
import math
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, LineString, MultiLineString
from shapely.ops import split
from pyproj import CRS


def parse_args():
    parser = argparse.ArgumentParser(description="Compute Cycling Quality Index and generate offset lines for road network")
    parser.add_argument(
        "--input",
        default=r"E:\Lenovo\Desktop\cycle\scr\test\data\export_outcome2.geojson",
        help="Input folder or file (GeoJSON/GPKG)"
    )
    parser.add_argument(
        "--layers", nargs="+", default=None,
        help="Layer names if input is multi-layer GeoPackage"
    )
    parser.add_argument(
        "--output",
        default=r"E:\Lenovo\Desktop\cycle\scr\test\data\export_outcome3.geojson",
        help="Output GeoPackage or GeoJSON path"
    )
    parser.add_argument(
        "--crs_metric", default="EPSG:3857",
        help="Projected CRS for metric calculations"
    )
    parser.add_argument(
        "--point_spacing", type=float, default=20.0,
        help="Spacing (m) to generate points along edges"
    )
    parser.add_argument(
        "--buffer_distance", type=float, default=5.0,
        help="Buffer distance (m) around points for sidepath detection"
    )
    parser.add_argument(
        "--min_length", type=float, default=10.0,
        help="Minimum edge length (m) to keep"
    )
    parser.add_argument(
        "--offset_distance", type=float, default=2.0,
        help="Distance (m) to offset lines left and right"
    )
    return parser.parse_args()


def extract_numeric(val):
    if val is None:
        return None
    m = re.search(r"\d+", str(val))
    return float(m.group()) if m else None


def remove_deadends(gdf):
    endpoints = []
    for geom in gdf.geometry:
        if isinstance(geom, LineString):
            coords = list(geom.coords)
            endpoints.extend([(coords[0][0], coords[0][1]), (coords[-1][0], coords[-1][1])])
    counts = pd.Series(endpoints).value_counts()
    dead_coords = set(counts[counts == 1].index)
    def is_dead(geom):
        if not isinstance(geom, LineString): return False
        start = (geom.coords[0][0], geom.coords[0][1])
        end = (geom.coords[-1][0], geom.coords[-1][1])
        return start in dead_coords or end in dead_coords
    return gdf[~gdf.geometry.apply(is_dead)].copy()


def generate_points_along(gdf, dist):
    pts, ids = [], []
    for idx, row in gdf.iterrows():
        line = row.geometry
        if not isinstance(line, LineString): continue
        n = math.floor(line.length / dist)
        for i in range(n + 1):
            pts.append(line.interpolate(i * dist))
            ids.append(idx)
    return gpd.GeoDataFrame({"edge_id": ids}, geometry=pts, crs=gdf.crs)


def compute_sidepath_presence(ways, pts_gdf, buf_dist):
    buf = pts_gdf.copy()
    buf['geometry'] = buf.geometry.buffer(buf_dist)
    buf = buf.set_geometry('geometry')
    joined = gpd.sjoin(buf, ways, how="left", predicate="intersects")
    presence = joined.groupby("edge_id")["index_right"].apply(lambda x: x.notna().any())
    return presence.to_dict()


def generate_offset_lines(gdf, offset_dist):
    """
    Generate left and right offset lines for each LineString feature.
    Returns a GeoDataFrame with columns ['edge_id', 'side', 'geometry'].
    """
    offs, ids, sides = [], [], []
    for idx, row in gdf.iterrows():
        line = row.geometry
        if not isinstance(line, LineString): continue
        # create left offset
        try:
            left = line.parallel_offset(offset_dist, 'left', join_style=2)
            right = line.parallel_offset(offset_dist, 'right', join_style=2)
        except Exception:
            continue
        # flatten MultiLineString
        for geom, side in [(left, 'left'), (right, 'right')]:
            if isinstance(geom, (LineString, MultiLineString)):
                offs.append(geom)
                ids.append(idx)
                sides.append(side)
    return gpd.GeoDataFrame({"edge_id": ids, "side": sides}, geometry=offs, crs=gdf.crs)


def compute_quality_index(df):
    w_speed, w_barrier, w_side = 0.4, 0.3, 0.3
    df["speed_norm"] = df["proc_maxspeed"].clip(0, 60) / 60
    df["barrier_score"] = df["has_physical_barrier"].astype(int)
    df["side_score"] = df["sidepath_presence"].astype(int)
    df["cqi"] = (w_barrier * df["barrier_score"]
                  + w_side * df["side_score"]
                  + w_speed * (1 - df["speed_norm"]))
    return df


def main():
    args = parse_args()
    # 1. Load input
    if os.path.isdir(args.input):
        files = glob.glob(os.path.join(args.input, "*.geojson"))
        gdfs = [gpd.read_file(f) for f in files]
        ways = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=gdfs[0].crs)
    else:
        if args.layers:
            gdfs = [gpd.read_file(args.input, layer=l) for l in args.layers]
            ways = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=gdfs[0].crs)
        else:
            ways = gpd.read_file(args.input)

    # 2. Reproject
    ways = ways.to_crs(args.crs_metric)

    # 3. Retain and rename fields
    keep = ["highway", "cycleway", "cycleway:left", "cycleway:right",
            "cycleway:both", "cycleway:segregated", "bicycle", "lanes",
            "maxspeed", "name", "surface", "lit", "oneway"]
    for f in keep:
        ways[f] = ways.get(f)
    ways = ways.rename(columns={c: c.replace(':', '_') for c in keep})
    ways = ways[[c.replace(':', '_') for c in keep] + ["geometry"]].copy()

    # 4. Clean edges
    ways = remove_deadends(ways)
    ways['length_m'] = ways.geometry.length
    ways = ways[ways['length_m'] >= args.min_length].copy()

    # 5. Sidepath detection
    pts = generate_points_along(ways, args.point_spacing)
    side_dict = compute_sidepath_presence(ways, pts, args.buffer_distance)
    ways['sidepath_presence'] = ways.index.map(side_dict).fillna(False)

    # 6. Offset lines
    offsets = generate_offset_lines(ways, args.offset_distance)

    # 7. Attribute calculations
    ways['proc_maxspeed'] = ways['maxspeed'].apply(extract_numeric)
    def has_barrier(r):
        for v in [r['cycleway'], r['cycleway_left'], r['cycleway_right'],
                  r['cycleway_both'], r['cycleway_segregated']]:
            if v and str(v).lower() in ['track', 'separate', 'yes']:
                return True
        return False
    ways['has_physical_barrier'] = ways.apply(has_barrier, axis=1)
    ways = compute_quality_index(ways)

    # 8. Write output
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    ext = os.path.splitext(args.output)[1].lower()
    driver = 'GeoJSON' if ext in ['.geojson', '.json'] else 'GPKG'
    # write main layer
    ways.to_file(args.output, layer='cqi', driver=driver)
    # write offsets as separate layer (for GPKG) or separate file for GeoJSON
    if driver == 'GPKG':
        offsets.to_file(args.output, layer='offset_lines', driver='GPKG')
    else:
        out_off = os.path.splitext(args.output)[0] + '_offsets.geojson'
        offsets.to_file(out_off, driver='GeoJSON')
    print(f"✅ Done. Main output: {args.output}, offsets: {'embedded in GPKG' if driver=='GPKG' else out_off}")

if __name__ == '__main__':
    main()
