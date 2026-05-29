from pydantic import BaseModel, ConfigDict


class ExcelBase(BaseModel):
    """Excel基础模型"""
    message: str
    status: int


class ExcelImportResponse(ExcelBase):
    """Excel导入响应模型"""
    imported_rows: int
    failed_rows: int | None = 0
    new_rows: int | None = 0  # 新增的记录数
    updated_rows: int | None = 0  # 更新的记录数
    duplicate_rows: int | None = 0  # Excel内部重复的行数
    error_details: list[str] | None = None


class ExcelExportResponse(ExcelBase):
    """Excel导出响应模型"""
    file_url: str
    file_name: str
    exported_rows: int


class ExcelInDBBase(ExcelBase):
    """数据库中的Excel模型"""
    id: int

    model_config = ConfigDict(from_attributes=True)
