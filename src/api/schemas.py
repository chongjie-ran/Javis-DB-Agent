"""API请求/响应模型"""
from pydantic import BaseModel, Field
from typing import Optional, Any


# ============ 请求模型 ============

class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话ID，不传则创建新会话")
    user_id: Optional[str] = Field("anonymous", description="用户ID")
    agent: Optional[str] = Field(None, description="指定Agent (orchestrator/diagnostic/risk/sql_analyzer/inspector/reporter)")
    context: dict = Field(default_factory=dict, description="额外上下文")


class DiagnoseRequest(BaseModel):
    """告警诊断请求"""
    alert_id: str = Field(..., description="告警ID")
    instance_id: Optional[str] = Field(None, description="实例ID")
    context: dict = Field(default_factory=dict)


class SQLAnalyzeRequest(BaseModel):
    """SQL分析请求"""
    sql: Optional[str] = Field(None, description="SQL文本")
    sql_id: Optional[str] = Field(None, description="SQL ID")
    session_id: Optional[str] = Field(None, description="会话ID")
    instance_id: Optional[str] = Field(None, description="实例ID")


class InspectRequest(BaseModel):
    """巡检请求"""
    instance_ids: list[str] = Field(..., description="实例ID列表")
    inspection_type: str = Field("quick", description="巡检类型: quick/full/security")


class ReportRequest(BaseModel):
    """报告生成请求"""
    report_type: str = Field(..., description="报告类型: rca/inspection/summary")
    instance_id: Optional[str] = Field(None, description="实例ID")
    incident_id: Optional[str] = Field(None, description="事件ID")
    data: str = Field("", description="报告数据")


# ============ 响应模型 ============

class APIResponse(BaseModel):
    """通用API响应"""
    code: int = Field(0, description="状态码: 0成功，其他失败")
    message: str = Field("success", description="消息")
    data: Any = Field(None, description="数据")


class ChatResponse(BaseModel):
    """对话响应"""
    code: int = 0
    message: str = "success"
    session_id: str
    reply: str
    agent: str = "orchestrator"
    metadata: dict = {}


class DiagnoseResponse(BaseModel):
    """诊断响应"""
    code: int = 0
    message: str = "success"
    data: dict = {}


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "healthy"
    version: str = ""
    ollama_status: str = ""
    timestamp: float = 0
    metadata: dict = {}
