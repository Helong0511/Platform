"""
服务层模块包。

功能说明：
- 将业务逻辑从 API endpoints 抽离，统一由 Service 类封装
- 负责权限校验、数据验证、事务编排；数据访问通过 Repository 或 ORM 查询

在系统中的位置：
- 被 ``app.api_v1`` 各路由注入调用；复杂子域按目录划分（``ad_data``、``cpl``、``tracking``）

注意事项：
1. 服务层不直接处理 HTTP 请求/响应，异常通过 ``raise_api_exception`` 向上抛出
2. 新增服务应继承 ``BaseService`` 并复用其权限检查方法
"""
