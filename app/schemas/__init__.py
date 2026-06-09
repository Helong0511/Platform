"""Pydantic Schema 统一入口

职责：为 API 请求/响应提供数据校验与序列化模型，按业务域分子模块组织。

子模块：auth、user、client、product、ad_data、cpl、postback、cloak 等。

说明：请求/响应 JSON 结构定义，供 FastAPI 自动校验与 OpenAPI 文档生成。
说明：包入口，聚合子模块 router 或导出 Schema 供上层引用。

说明：Schema 包入口，按业务域导出 Pydantic 模型。"""
