import os, re, glob
import geopandas as gpd
import pandas as pd

# ========== 配置 ==========
# 原始分块目录（9 个文件所在的目录）
ORIG_DIR = r"/content/drive/MyDrive/CASA0004_Cycling/data/s1/Roads_OT/CQI_1"
# 禁止集分块目录（如果“每个分块都有一份禁止文件”，填它的目录；否则留空，使用 BAN_MASTER_FILE）
BAN_DIR  = r""  # 例如："/content/drive/.../ban_chunks"；没有就留空
# 单个全域禁止文件（如果有一份覆盖全域的“禁止文件”，填它；若使用 BAN_DIR 则留空）
BAN_MASTER_FILE = r""  # 例如："/content/drive/.../ban_master.geojson"

# 输出目录
OUT_DIR = r"/content/drive/MyDrive/CASA0004_Cycling/data/s1/Roads_OT/CQI_final"

# 原始文件的匹配模式（默认取目录下所有 geojson）
ORIG_PATTERN = "*.geojson"

# 原始与禁止文件如何“配对”的 key：默认用文件名前缀第一个数字块，如 1_xxx.geojson → key=1
def file_key(path: str) -> str:
    name = os.path.basename(path)
    # 提取第一个连续数字作为 key；找不到则去掉扩展名后全名做 key
    m = re.search(r"(\d+)", name)
    return m.group(1) if m else os.path.splitext(name)[0]

# ========== 工具函数 ==========
def detect_id_column(gdf: gpd.GeoDataFrame) -> str:
    """在常见字段名中检测 id 列"""
    candidates = ["id", "@id", "osm_id", "osm_way_id"]
    cols = {c.lower(): c for c in gdf.columns}
    for c in candidates:
        if c in cols:
            return cols[c]
    # 兜底：找含 "id" 的列
    for c in gdf.columns:
        if "id" in c.lower():
            return c
    raise ValueError("未找到 id 字段，请检查字段名（期望 id/@id/osm_id/osm_way_id）")

def normalize_id_series(s: pd.Series) -> pd.DataFrame:
    """
    生成两列：
      id_str: 原样字符串（去首尾空格）
      id_num: 仅数字部分（way/123 -> 123；relation/456 -> 456）
    """
    s = s.astype(str).str.strip()
    id_num = s.str.extract(r"(\d+)", expand=False).fillna("")
    return pd.DataFrame({"id_str": s, "id_num": id_num})

def build_ban_sets(ban_gdf: gpd.GeoDataFrame, ban_id_col: str):
    ndf = normalize_id_series(ban_gdf[ban_id_col])
    ban_full = set(ndf["id_str"].tolist())
    ban_num  = set([x for x in ndf["id_num"].tolist() if x])
    return ban_full, ban_num

def subtract_by_id(orig_gdf: gpd.GeoDataFrame, ban_full: set, ban_num: set, orig_id_col: str) -> gpd.GeoDataFrame:
    ndf = normalize_id_series(orig_gdf[orig_id_col])
    mask_drop = ndf["id_str"].isin(ban_full) | (ndf["id_num"].isin(ban_num) & ndf["id_num"].ne(""))
    kept = orig_gdf.loc[~mask_drop].copy()
    return kept

# ========== 主流程 ==========
os.makedirs(OUT_DIR, exist_ok=True)

# 收集原始分块
orig_files = sorted(glob.glob(os.path.join(ORIG_DIR, ORIG_PATTERN)))
if not orig_files:
    raise SystemExit(f"在 {ORIG_DIR} 下没有找到匹配 {ORIG_PATTERN} 的原始文件")

# 构建 key→原始文件映射
orig_map = {file_key(p): p for p in orig_files}

# 准备禁止集合
ban_map = {}
if BAN_DIR:
    ban_files = sorted(glob.glob(os.path.join(BAN_DIR, "*.geojson")))
    ban_map = {file_key(p): p for p in ban_files}
    print(f"使用分块禁止集：{len(ban_map)} 个文件")
elif BAN_MASTER_FILE:
    if not os.path.exists(BAN_MASTER_FILE):
        raise SystemExit(f"未找到 BAN_MASTER_FILE: {BAN_MASTER_FILE}")
    print(f"使用全域禁止文件：{BAN_MASTER_FILE}")
else:
    raise SystemExit("请设置 BAN_DIR 或 BAN_MASTER_FILE 之一。")

# 如果用全域禁止文件，预先读入并构建集合（一次就够）
global_ban_full = global_ban_num = None
if BAN_MASTER_FILE:
    ban_all = gpd.read_file(BAN_MASTER_FILE)
    ban_id_col = detect_id_column(ban_all)
    global_ban_full, global_ban_num = build_ban_sets(ban_all, ban_id_col)
    print(f"全域禁止集：string={len(global_ban_full)}, numeric={len(global_ban_num)}")

# 遍历处理
for k, orig_path in orig_map.items():
    print("="*60)
    print(f"处理分块 key={k} | 原始：{os.path.basename(orig_path)}")

    # 读取原始
    orig = gpd.read_file(orig_path)
    orig_id_col = detect_id_column(orig)

    # 确定本块使用的禁止集合
    if BAN_DIR:
        ban_path = ban_map.get(k)
        if ban_path is None:
            print(f"[警告] 未找到 key={k} 的禁止文件，跳过此块")
            continue
        ban = gpd.read_file(ban_path)
        ban_id_col = detect_id_column(ban)
        ban_full, ban_num = build_ban_sets(ban, ban_id_col)
    else:
        # 用全域禁止
        ban_full, ban_num = global_ban_full, global_ban_num

    # 执行按 id 相减
    kept = subtract_by_id(orig, ban_full, ban_num, orig_id_col)

    # 输出路径（保留原文件名）
    out_name = os.path.basename(orig_path)
    out_path = os.path.join(OUT_DIR, out_name)
    kept.to_file(out_path, driver="GeoJSON")

    print(f"原始 {len(orig)} 条 → 删除 {len(orig)-len(kept)} 条 → 保留 {len(kept)} 条")
    print(f"已保存：{out_path}")

print("✅ 全部完成！")
