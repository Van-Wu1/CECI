from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsWkbTypes,
    QgsProject,
    QgsPointXY,
    QgsField,
    edit,
)
from PyQt5.QtCore import QVariant

import statistics


def densify_layer_by_distance(src_layer, interval_m):
    """
    按固定距离加密几何（等距加点），返回内存图层。
    不依赖 processing 算法。
    """
    crs_auth = src_layer.crs().authid()  # e.g. 'EPSG:27700'
    wkb = src_layer.wkbType()
    geom_str = "MultiLineString" if QgsWkbTypes.isMultiType(wkb) else "LineString"
    mem = QgsVectorLayer(f"{geom_str}?crs={crs_auth}", f"{src_layer.name()}_densified", "memory")
    prov = mem.dataProvider()
    prov.addAttributes(src_layer.fields())
    mem.updateFields()

    feats = []
    for f in src_layer.getFeatures():
        g = f.geometry()
        if not g or g.isEmpty():
            continue
        try:
            dg = g.densifyByDistance(float(interval_m))
        except Exception:
            dg = g
        nf = QgsFeature(mem.fields())
        nf.setAttributes(f.attributes())
        nf.setGeometry(dg)
        feats.append(nf)

    if feats:
        prov.addFeatures(feats)
        mem.updateExtents()
    return mem


from qgis.core import QgsProject, QgsCoordinateTransform, QgsPointXY

def sample_raster_values_at_vertices(line_layer, raster_layer):
    """
    沿线每个顶点采样坡度值，返回 {feature_id: [vals]}。
    使用 line_layer 的 CRS -> raster_layer 的 CRS 做坐标变换。
    """
    provider   = raster_layer.dataProvider()
    raster_crs = raster_layer.crs()
    src_crs    = line_layer.crs()

    # 用项目的 transform context
    xform = QgsCoordinateTransform(src_crs, raster_crs, QgsProject.instance()) if src_crs != raster_crs else None

    # nodata（可选）
    try:
        nodata = provider.sourceNoDataValue(1)
    except Exception:
        nodata = None

    values_dict = {}
    for feat in line_layer.getFeatures():
        fid  = feat.id()
        geom = feat.geometry()
        vals = []
        if not geom or geom.isEmpty():
            values_dict[fid] = vals
            continue

        for v in geom.vertices():
            pt = QgsPointXY(v)
            if xform:
                try:
                    pt = xform.transform(pt)
                except Exception:
                    continue
            try:
                val, ok = provider.sample(pt, 1)   # band=1
            except Exception:
                val, ok = (None, False)

            if not ok:
                continue
            if nodata is not None and val == nodata:
                continue
            try:
                vals.append(float(val))
            except (TypeError, ValueError):
                pass

        values_dict[fid] = vals

    return values_dict

    """
    沿线每个顶点采样坡度值，返回 {feature_id: [vals]} 字典
    """
    if isinstance(target_crs_epsg, str):
        target_crs_epsg = target_crs_epsg.replace("EPSG:", "").strip()
    target_crs = QgsCoordinateReferenceSystem.fromEpsgId(int(target_crs_epsg))

    raster_provider = raster_layer.dataProvider()
    raster_crs = raster_layer.crs()
    transform = QgsCoordinateTransform(target_crs, raster_crs, raster_layer.dataProvider().transformContext())

    values_dict = {}
    for feat in line_layer.getFeatures():
        fid = feat.id()
        geom = feat.geometry()
        vals = []
        for vertex in geom.vertices():
            pt = transform.transform(vertex)
            ident = raster_provider.sample(pt, 1)  # band=1
            if ident[1]:
                try:
                    val = float(ident[0])
                    vals.append(val)
                except (ValueError, TypeError):
                    pass
        values_dict[fid] = vals
    return values_dict


def calc_stat(values, choice="q3"):
    """
    根据 choice 计算统计值，choice ∈ {'q3', 'max', 'mean'}
    """
    if not values:
        return None
    if choice == "max":
        return max(values)
    elif choice == "mean":
        return statistics.mean(values)
    elif choice == "q3":
        try:
            return statistics.quantiles(values, n=4)[2]
        except Exception:
            return max(values)
    else:
        return max(values)


def apply_slope_factor(
    roads_layer,
    slope_raster,
    id_field,
    target_crs_epsg,
    sample_interval_m=20,
    slope_unit="degree",  # 'degree' or 'percent'
    stat_choice="q3",
    overwrite=True
):
    """
    为道路图层计算坡度因子 fac_3 和 proc_slope 字段
    """
    # 确保坡度栅格是 QgsRasterLayer
    if isinstance(slope_raster, str):
        slope_raster = QgsRasterLayer(slope_raster, "slope_raster")
        if not slope_raster.isValid():
            raise RuntimeError("坡度栅格无效")

    # 加密几何
    densified = densify_layer_by_distance(roads_layer, sample_interval_m)

    # 采样
    values_dict = sample_raster_values_at_vertices(densified, slope_raster)


    # 确保字段存在
    prov = roads_layer.dataProvider()
    field_names = [f.name() for f in prov.fields()]
    if "proc_slope" not in field_names:
        prov.addAttributes([QgsField("proc_slope", QVariant.Double)])
    if "fac_3" not in field_names:
        prov.addAttributes([QgsField("fac_3", QVariant.Double)])
    roads_layer.updateFields()

    # 回写
    with edit(roads_layer):
        for feat in roads_layer.getFeatures():
            fid = feat.id()
            vals = values_dict.get(fid, [])
            slope_val = calc_stat(vals, stat_choice)
            if slope_val is None:
                slope_val = 0.0
                fac_3 = 1.0
            else:
                # 如果是角度单位，先转百分比
                if slope_unit == "degree":
                    import math
                    slope_val = math.tan(math.radians(slope_val)) * 100.0
                fac_3 = slope_to_factor(slope_val)
            roads_layer.changeAttributeValue(fid, roads_layer.fields().indexFromName("proc_slope"), round(slope_val, 2))
            roads_layer.changeAttributeValue(fid, roads_layer.fields().indexFromName("fac_3"), round(fac_3, 2))

    return roads_layer


def slope_to_factor(slope_percent):
    """
    将坡度百分比映射为因子（示例规则，可按需调整）
    """
    if slope_percent <= 2:
        return 1.0
    elif slope_percent <= 4:
        return 0.9
    elif slope_percent <= 6:
        return 0.75
    elif slope_percent <= 8:
        return 0.6
    elif slope_percent <= 10:
        return 0.45
    else:
        return 0.3
