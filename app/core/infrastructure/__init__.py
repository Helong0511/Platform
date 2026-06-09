"""
基础设施层（app/core/infrastructure）。

提供缓存抽象（Redis/内存）、兼容层、高级防护（穿透/击穿/雪崩）与指标采集，
供业务模块与 cache_compat 统一调用，与旧版 cache.py 并存过渡。
"""

