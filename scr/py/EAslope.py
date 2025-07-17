import os
import requests
import zipfile
import io

# 下载目录
output_folder = "./data/EA_LiDAR_Tiles_London"
os.makedirs(output_folder, exist_ok=True)

# 真实存在的 EA LiDAR Tile 编号
tile_codes = [
    "TQ28se", "TQ28sw", "TQ28ne", "TQ28nw",
    "TQ38se", "TQ38sw", "TQ38ne", "TQ38nw",
    "TQ37ne", "TQ37nw", "TQ37se", "TQ37sw"
]

# 使用正式下载接口
# ✅ 修正链接格式（可直接下载 zip）
def get_url(tile):
    return f"https://environment.data.gov.uk/ds/survey/get?grid={tile}&product=DTM_1m&year=2022"


# 下载函数
def download_and_extract(tile):
    url = get_url(tile)
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200 and "zip" in response.headers.get("Content-Type", ""):
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                z.extractall(os.path.join(output_folder, tile))
            print(f"✅ 下载成功：{tile}")
        else:
            print(f"⚠️ 无法下载（无内容）：{tile}")
    except Exception as e:
        print(f"❌ 下载失败：{tile} —— {e}")

# 下载开始
for tile in tile_codes:
    download_and_extract(tile)
