# QGIS/CPython 通用热重载小工具
# 用法示例在文件末尾

import importlib, sys, os, time, inspect

def hot_reload(module_name, attrs=None, verify_substring=None, inject_globals=True):
    """
    热重载一个模块并可选地重新绑定其中的函数/类到当前全局命名空间。

    module_name: 模块名字符串，如 "beta_slope_factor"
    attrs: 需要从模块里重新绑定的对象名列表，比如 ["apply_slope_factor"]
    verify_substring: 可选，在源码里查一个关键字（比如老报错文案），方便确认已清除
    inject_globals: 是否把 attrs 直接塞进当前 globals()

    返回: (module, bound) 其中 bound 是 {name: obj}
    """
    # 1) 彻底清掉可能的缓存（包含子模块）
    to_delete = [m for m in list(sys.modules.keys()) if m == module_name or m.startswith(module_name + ".")]
    for m in to_delete:
        del sys.modules[m]

    # 2) 重新导入并 reload（双保险）
    mod = importlib.import_module(module_name)
    mod = importlib.reload(mod)

    # 3) 打印加载信息
    path = getattr(mod, "__file__", "<unknown>")
    mtime = time.ctime(os.path.getmtime(path)) if os.path.exists(path) else "N/A"
    ver = getattr(mod, "__version__", "(no __version__)")
    print(f"[hot_reload] USING: {path}")
    print(f"[hot_reload] MTIME: {mtime}")
    print(f"[hot_reload] VERSION: {ver}")

    # 4) 可选：核查源码里是否还包含某个旧字符串（比如旧的 raise 文案）
    if verify_substring:
        try:
            with open(path, "r", encoding="utf-8") as f:
                src = f.read()
            hit = verify_substring in src
            print(f"[hot_reload] CONTAINS '{verify_substring}': {hit}")
        except Exception as e:
            print(f"[hot_reload] verify_substring check failed: {e}")

    # 5) 重新绑定函数/类到当前全局（避免旧引用问题）
    bound = {}
    if attrs:
        for name in attrs:
            if hasattr(mod, name):
                obj = getattr(mod, name)
                bound[name] = obj
                if inject_globals:
                    globals()[name] = obj
                # 显示对象来自哪个文件（再次确认不是旧引用）
                try:
                    sf = inspect.getsourcefile(obj) or "<built-in>"
                except Exception:
                    sf = "<unknown>"
                print(f"[hot_reload] bound {name} from {sf}")
            else:
                print(f"[hot_reload] WARNING: '{module_name}' has no attribute '{name}'")

    return mod, bound


# -----------------------
# 用法示例（你可以按需修改）：
# -----------------------
# 目标：重载 beta_slope_factor，并把 apply_slope_factor 重新绑定到当前会话
# 同时检查旧文案是否还在（比如你以前的报错文案）
#
# mod, bound = hot_reload(
#     module_name="beta_slope_factor",            # 如果你用了 *_fixed 就改名字
#     attrs=["apply_slope_factor"],
#     verify_substring="No slope stats available to map"
# )
#
# 之后直接用：
# result_layer = apply_slope_factor(
#     roads_layer=layer,
#     slope_raster="D:/data/slope.tif",
#     id_field="id",
#     target_crs_epsg=27700,     # 或 p.crs_metric
#     sample_interval_m=20,
#     slope_unit="degree",
#     stat_choice="max",         # 'q3'/'max'/'mean'
#     overwrite=True
# )
