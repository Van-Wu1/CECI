# 如果没装 remotes 包，先装它
install.packages("remotes")
remotes::install_github("h-a-graham/EAlidaR")



library(EAlidaR)
library(sf)

# 你可以直接用 EA_BNG("Greater London") 来获取边界（EPSG:27700）
bbox <- EA_BNG("Greater London")  # 返回 sf polygon

# 检查能下载哪些 tile
tiles <- available_tiles(bbox = bbox, dataset = "composite", product = "DTM", resolution = 1)



# 下载并保存 DEM（默认保存为 GeoTIFF）
download_tiles(
  tiles = tiles,
  folder = "lidar_london",     # 本地保存文件夹
  dataset = "composite",
  product = "DTM",
  resolution = 1,
  year = 2022
)
