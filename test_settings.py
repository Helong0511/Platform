from app.core.config import settings

print(f"PRODUCTION_ENV: {settings.PRODUCTION_ENV}")
print(f"is_production: {settings.is_production}")
print(f"API_V1_STR: {settings.API_V1_STR}")
print(f"BACKEND_CORS_ORIGINS: {settings.BACKEND_CORS_ORIGINS}")