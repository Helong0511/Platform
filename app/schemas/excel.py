"""Excel 导入/导出 API 响应 Schema。

描述批量导入行数统计、失败原因汇总等结构化返回体。

说明：请求/响应 JSON 结构定义，供 FastAPI 自动校验与 OpenAPI 文档生成。

说明：Excel 批量导入/导出，支持广告数据等业务的表格批处理。"""
from pydantic import BaseModel, ConfigDict


class ExcelBase(BaseModel):
    """
    Excel基础模型
    
    继承 BaseModel。公共字段基类，供 Create/Update/Response 等模型复用。
    """
    message: str
    """
    Excel导入响应模型
    
    继承 ExcelBase。单条或列表项的 API 响应数据结构。
    """


class ExcelImportResponse(ExcelBase):
    """Excel 导入响应模型。"""
    status: int = 200
    imported_rows: int
    failed_rows: int = 0
    new_rows: int | None = 0
    updated_rows: int | None = 0
    duplicate_rows: int | None = 0
    error_details: list[str] | None = None


class ExcelExportResponse(ExcelBase):
    """
    Excel导出响应模型
    
    API 响应数据结构，用于序列化数据库记录或业务计算结果。
    """
    file_url: str
    file_name: str
    exported_rows: int


class ExcelInDBBase(ExcelBase):
    """
    数据库中的Excel模型
    
    公共字段基类，供 Create/Update/Response 等子模型复用，避免重复定义。
    """
    id: int

    model_config = ConfigDict(from_attributes=True)
