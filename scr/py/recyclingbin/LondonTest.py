import os
import osmnx as ox
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# -------------------------------
# LTS 估算函数
def estimate_lts_conveyal(functional_class, has_bike_lane, speed_limit, lane_count):
    if speed_limit is None:
        speed_limit = {
            "residential": 25,
            "tertiary": 30,
            "secondary": 35,
            "primary": 40,
            "trunk": 45
        }.get(functional_class, 35)
    if lane_count is None:
        lane_count = {
            "residential": 2,
            "tertiary": 2,
            "secondary": 3,
            "primary": 4,
            "trunk": 4
        }.get(functional_class, 3)
    if has_bike_lane is None:
        has_bike_lane = False

    if functional_class in ["residential", "living_street"] and has_bike_lane and speed_limit <= 25:
        return 1
    elif has_bike_lane and speed_limit <= 30 and lane_count <= 2:
        return 2
    elif not has_bike_lane and functional_class in ["residential", "tertiary"] and speed_limit <= 30:
        return 3
    elif lane_count >= 4 or speed_limit >= 45:
        return 4
    elif functional_class in ["primary", "secondary", "trunk"] and not has_bike_lane:
        return 4
    elif has_bike_lane and speed_limit > 35:
        return 3
    else:
        return 2

# -------------------------------
# 下载伦敦边界
place_name = "London, England, United Kingdom"
gdf = ox.geocode_to_gdf(place_name)

# 使用过滤器：抓取适合骑行的所有道路（含 cycleway 等）
custom_filter = (
    '["highway"]["area"!~"yes"]'
    '["highway"!~"abandoned|bus_guideway|construction|corridor|elevator|escalator|footway|'
    'motor|no|planned|platform|proposed|raceway|razed|steps"]'
    '["bicycle"!~"no"]["service"!~"private"]'
)

print("📥 正在下载伦敦骑行道路数据...")
graph = ox.graph_from_polygon(gdf.geometry[0], custom_filter=custom_filter)
edges = ox.graph_to_gdfs(graph, nodes=False)

# -------------------------------
# 数据预处理
def to_bool(val):
    if val in [True, "yes", "Yes", "YES", "lane", "track"]:
        return True
    return False

edges["functional_class"] = edges["highway"].astype(str)
edges["has_bike_lane"] = edges["cycleway"].astype(str).apply(lambda x: to_bool(x) if x != "nan" else False) if "cycleway" in edges.columns else False
edges["speed_limit"] = edges["maxspeed"].apply(
    lambda x: float(x.split()[0]) if isinstance(x, str) and x.split()[0].isdigit() else None
)
edges["lane_count"] = edges["lanes"].apply(
    lambda x: int(x) if isinstance(x, str) and x.isdigit() else None
)

# -------------------------------
# LTS 估算
print("🧠 正在估算 LTS 等级...")
edges["lts"] = edges.apply(
    lambda row: estimate_lts_conveyal(
        row["functional_class"],
        row["has_bike_lane"],
        row["speed_limit"],
        row["lane_count"]
    ),
    axis=1
)

# -------------------------------
# 导出为 GeoJSON
output_dir = "../data"
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, "london_highway_lts.geojson")
edges.to_file(output_path, driver="GeoJSON")
print(f"✅ LTS 数据导出成功：{output_path}")

# -------------------------------
# 可视化
print("🎨 正在绘图...")
lts_colors = {
    1: "#2ECC71",   # green
    2: "#F1C40F",   # yellow
    3: "#E67E22",   # orange
    4: "#E74C3C"    # red
}
edges["color"] = edges["lts"].map(lts_colors)

fig, ax = plt.subplots(figsize=(12, 12))
edges.plot(ax=ax, linewidth=0.5, color=edges["color"])
ax.set_title("London Road Network - Level of Traffic Stress (LTS)", fontsize=16)
ax.axis("off")

# 图例
legend_elements = [
    Line2D([0], [0], color=lts_colors[1], lw=2, label="LTS 1 (最安全)"),
    Line2D([0], [0], color=lts_colors[2], lw=2, label="LTS 2"),
    Line2D([0], [0], color=lts_colors[3], lw=2, label="LTS 3"),
    Line2D([0], [0], color=lts_colors[4], lw=2, label="LTS 4 (高压力)")
]
ax.legend(handles=legend_elements, title="LTS 等级", loc="lower left")

plt.tight_layout()
plt.show()
