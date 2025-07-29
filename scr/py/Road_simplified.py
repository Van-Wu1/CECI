import osmnx as ox
import geopandas as gpd
import networkx as nx

# === 1. 获取 Greater London 边界 ===
place_name = "Greater London, United Kingdom"
gdf = ox.geocode_to_gdf(place_name)

# === 2. 自定义过滤器：允许骑行的道路 ===
custom_filter = (
    '["highway"]["area"!~"yes"]'
    '["highway"!~"abandoned|bus_guideway|construction|corridor|elevator|escalator|footway|'
    'motor|no|planned|platform|proposed|raceway|razed|steps"]'
    '["bicycle"!~"no"]["access"!~"private"]'
)

# === 3. 下载骑行网络 ===
print("正在抓取骑行网络数据（超级慢）...")
graph = ox.graph_from_polygon(gdf.geometry[0], custom_filter=custom_filter, simplify=True)
G = graph

# === 4. 清洗图结构：最大连通分量 + 转无向图 ===
if G.is_directed():
    comps = nx.weakly_connected_components(G)
else:
    comps = nx.connected_components(G)
largest_cc = max(comps, key=len)
G = G.subgraph(largest_cc).copy().to_undirected()

# === 5. 删除死胡同（度为1节点）===
deadends = [n for n in G.nodes if G.degree[n] == 1]
G.remove_nodes_from(deadends)

# === 6. 删除长度 <10m 的边 ===
short_edges = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True) if d.get("length", 0) < 10]
G.remove_edges_from(short_edges)

# 6. 转为 GeoDataFrame
nodes, edges = ox.graph_to_gdfs(G)

# 7. 修复字段类型，避免被 GeoPandas 吃掉
fields_to_fix = ['highway', 'name', 'ref', 'bridge', 'tunnel', 'service', 'maxspeed', 'lanes', 'est_width']
for field in fields_to_fix:
    if field in edges.columns:
        edges[field] = edges[field].astype(str)

# 8. 导出图结构和边文件（只保留一个gpkg）
# ox.save_graphml(G, "london_bike_cleaned.graphml")
# edges.to_file("london_edges_FIXED.geojson", driver="GeoJSON") 
edges.to_file("london_edges_FIXED.gpkg", layer='edges', driver="GPKG")


print("导出完成：字段修复 + graphml + geojson 全部生成！")