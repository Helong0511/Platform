import os
os.environ["PRODUCTION_ENV"] = "development"

print("测试CSRF中间件的路径匹配逻辑...")

# 直接测试路径匹配
login_path = "/api/v1/auth/login"
print(f"\n直接测试路径匹配:")
print(f"测试路径: {login_path}")
print(f"路径 '/api/v1/auth/login' 等于 '/api/v1/auth/login': {login_path == '/api/v1/auth/login'}")
print(f"路径 '/api/v1/auth/login' 等于 '/api/v1/auth/logout': {login_path == '/api/v1/auth/logout'}")

# 手动测试should_skip_csrf_check的逻辑
method = "POST"
print(f"\n手动测试should_skip_csrf_check逻辑:")
print(f"1. 安全方法检查: {method.upper() in ['GET', 'HEAD', 'OPTIONS', 'TRACE']}")
print(f"2. 登录接口检查: {login_path == '/api/v1/auth/login' or login_path == '/api/v1/auth/logout'}")
print(f"3. 客户API接口检查: {login_path == '/api/v1/client_products' or login_path == '/api/v1/client_data'}")
print(f"4. Macan PostBack接口检查: {login_path == '/api/v1/macan/postback'}")
print(f"5. 客户端错误记录接口检查: {login_path == '/api/v1/audit-logs/client-error'}")
print(f"6. 静态资源检查: {login_path.startswith('/static/') or login_path.startswith('/assets/')}")
print(f"7. API文档检查: {login_path.startswith('/api/v1/docs') or login_path.startswith('/api/v1/redoc') or login_path.startswith('/api/v1/openapi.json')}")
print(f"8. 短链接重定向检查: {login_path.startswith('/s/')}")

# 测试CSRF中间件的跳过逻辑
should_skip = (
    method.upper() in ['GET', 'HEAD', 'OPTIONS', 'TRACE'] or
    login_path == '/api/v1/auth/login' or login_path == '/api/v1/auth/logout' or
    login_path == '/api/v1/client_products' or login_path == '/api/v1/client_data' or
    login_path == '/api/v1/macan/postback' or
    login_path == '/api/v1/audit-logs/client-error' or
    login_path.startswith('/static/') or login_path.startswith('/assets/') or
    login_path.startswith('/api/v1/docs') or login_path.startswith('/api/v1/redoc') or login_path.startswith('/api/v1/openapi.json') or
    login_path.startswith('/s/')
)

print(f"\n最终结果: should_skip = {should_skip}")

# 检查CSRF中间件的dispatch函数中的路径匹配
print(f"\n检查CSRF中间件dispatch函数中的路径匹配:")
print(f"1. 短链接重定向检查: {login_path.startswith('/s/')}")
print(f"2. 登录/登出接口检查: {login_path == '/api/v1/auth/login' or login_path == '/api/v1/auth/logout'}")
print(f"3. Macan PostBack接口检查: {login_path == '/api/v1/macan/postback'}")
print(f"4. 客户端错误记录接口检查: {login_path == '/api/v1/audit-logs/client-error'}")
print(f"5. 定时任务接口检查: {login_path.startswith('/api/v1/scheduled-tasks/')}")

# 检查CSRF中间件是否正确跳过登录接口
csrf_should_skip = (
    login_path.startswith('/s/') or
    login_path == '/api/v1/auth/login' or login_path == '/api/v1/auth/logout' or
    login_path == '/api/v1/macan/postback' or
    login_path == '/api/v1/audit-logs/client-error' or
    (login_path.startswith('/api/v1/scheduled-tasks/') and 
     (login_path.endswith('/trigger') or login_path.endswith('/reload') or login_path == '/api/v1/scheduled-tasks/reload-all'))
)

print(f"\nCSRF中间件dispatch函数中的跳过逻辑结果: {csrf_should_skip}")
