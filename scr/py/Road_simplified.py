# Google Colab

!pip install osmnx geopandas matplotlib


import osmnx as ox
import networkx as nx
import matplotlib.pyplot as plt


# === 1. 获取 Greater London 区域边界 ===
place_name = "Greater London, United Kingdom"
gdf = ox.geocode_to_gdf(place_name)

# === 2. 自定义过滤器：仅保留允许骑行的道路 ===
custom_filter = (
    '["highway"]["area"!~"yes"]'
    '["highway"!~"abandoned|bus_guideway|construction|corridor|elevator|escalator|footway|'
    'motor|no|planned|platform|proposed|raceway|razed|steps"]'
    '["bicycle"!~"no"]["service"!~"private"]'
)

# === 3. 下载骑行网络 ===
print("正在抓取骑行网络数据（Greater London，可能较慢）...")
graph = ox.graph_from_polygon(gdf.geometry[0], custom_filter=custom_filter, simplify=True)

G = graph

# 4. 提取最大连通分量（strongly=False 相当于“弱连通分量”）并转成无向图
if G.is_directed():
    # 如果是有向图，用弱连通分量
    comps = nx.weakly_connected_components(G)
else:
    # 如果已经是无向图，用连通分量
    comps = nx.connected_components(G)
# 选出最大的那个分量
largest_cc = max(comps, key=len)
# 在原 G 上切出子图并拷贝
G = G.subgraph(largest_cc).copy()
# 保证无向
G = G.to_undirected()

# 5. 删除死胡同（度为1）
deadends = [n for n in G.nodes if G.degree[n] == 1]
G.remove_nodes_from(deadends)

# 6. 删除边长 < 10m 的边
short_edges = [
    (u, v, k) 
    for u, v, k, d in G.edges(keys=True, data=True) 
    if d.get("length", 0) < 10
]
G.remove_edges_from(short_edges)

# 7. 打印基本统计信息
stats = ox.basic_stats(G)
print(f"📊 节点数: {stats['n']}")
print(f"📊 边数: {stats['m']}")
print(f"📊 总边长: {stats['edge_length_total']:.2f} 米")
print(f"📊 平均度: {stats['k_avg']:.2f}")
# print(f"📊 边密度: {stats['edge_density_km']:.2f} 条/km²")

# （可选）保存清洗后的网络
ox.save_graphml(G, "london_bike_cleaned.graphml")


import osmnx as ox
import geopandas as gpd

# 假设 G 已经是清洗好的无向图

# 把图转换成节点和边的 GeoDataFrame
nodes, edges = ox.graph_to_gdfs(G)

# 只保存边为 GeoJSON
edges.to_file("london_bike_cleaned_edges.geojson", driver="GeoJSON")

# 如果也想同时保存节点：
nodes.to_file("london_bike_cleaned_nodes.geojson", driver="GeoJSON")
