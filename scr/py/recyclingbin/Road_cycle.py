import osmnx as ox
import geopandas as gpd
import networkx as nx
import re

# 设置区域
place_name = "Greater London, United Kingdom"
gdf = ox.geocode_to_gdf(place_name)

# 设置自定义过滤器：抓取所有包含骑行相关标签的道路
custom_filter = (
    '["highway"]["area"!~"yes"]'
    '["highway"!~"abandoned|construction|platform|proposed|raceway|steps"]'
    '["bicycle"!~"no"]["access"!~"private"]'
)

print("📥 正在抓取含骑行功能的路网...")
G = ox.graph_from_polygon(gdf.geometry[0], custom_filter=custom_filter, simplify=True)

# 取最大连通分量
if G.is_directed():
    comps = nx.weakly_connected_components(G)
else:
    comps = nx.connected_components(G)
G = G.subgraph(max(comps, key=len)).copy().to_undirected()

# 删除死胡同
deadends = [n for n in G.nodes if G.degree[n] == 1]
G.remove_nodes_from(deadends)

# 删除超短边
short_edges = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True) if d.get("length", 0) < 10]
G.remove_edges_from(short_edges)

# 保留字段（包含 cycleway 相关 + 路网属性）
keep_tags = [
    "cycleway", "cycleway:left", "cycleway:right", "cycleway:both", "cycleway:segregated",
    "highway", "bicycle", "lanes", "maxspeed", "name", "surface", "lit", "oneway"
]

# 将字段写入属性中（替换冒号）
for u, v, k, d in G.edges(keys=True, data=True):
    for tag in keep_tags:
        if tag in d:
            d[tag.replace(":", "_")] = d[tag]

# 转为 GeoDataFrame
nodes, edges = ox.graph_to_gdfs(G)

# 清洗多值字段为字符串
def clean_field(val):
    if isinstance(val, list):
        return ";".join(map(str, val))
    return str(val) if val is not None else None

for field in [tag.replace(":", "_") for tag in keep_tags]:
    if field in edges.columns:
        edges[field] = edges[field].apply(clean_field)

# 添加物理隔断字段判断
def has_physical_barrier(row):
    values = [
        row.get('cycleway'),
        row.get('cycleway_left'),
        row.get('cycleway_right'),
        row.get('cycleway_both'),
        row.get('cycleway_segregated'),
    ]
    for val in values:
        if val:
            val = str(val).lower()
            if val in ['track', 'separate', 'yes']:
                return True
    return False

edges['has_physical_barrier'] = edges.apply(has_physical_barrier, axis=1)

# 导出为 GPKG
output_path = "bike.gpkg"
edges.to_file(output_path, layer="bike_edges", driver="GPKG")
print(f"导出完成：{output_path}")
