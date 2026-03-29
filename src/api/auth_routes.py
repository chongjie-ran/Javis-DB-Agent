"""认证API路由"""
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional
from src.api.auth import get_auth_manager, AuthManager
from src.api.schemas import APIResponse

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


def _get_token(authorization: str = Header(...)) -> str:
    """从Header提取Bearer token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header格式错误，需要 Bearer <token>")
    return authorization[7:]


def _get_current_user(token: str = Depends(_get_token)):
    """验证token并返回当前用户信息"""
    auth = get_auth_manager()
    payload = auth.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token无效或已过期")
    return payload


class LoginRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    code: int = 0
    message: str = "success"
    token: str = ""  # access_token
    refresh_token: str = ""  # refresh_token（有效期7天）
    token_type: str = "Bearer"
    expires_in: int = 86400
    user_id: str = ""
    username: str = ""
    role: str = ""


class TokenInfo(BaseModel):
    code: int = 0
    message: str = "success"
    user_id: str = ""
    username: str = ""
    role: str = ""
    exp: float = 0


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="刷新令牌")


class RefreshTokenResponse(BaseModel):
    code: int = 0
    message: str = "success"
    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "Bearer"
    expires_in: int = 86400


class RegisterRequest(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    role: str = Field("user", description="角色: user/admin")


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    用户登录
    
    返回JWT token，有效期24小时
    """
    auth = get_auth_manager()
    user = auth.authenticate(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    token, refresh_token = auth.create_token(user)
    return LoginResponse(
        token=token,
        refresh_token=refresh_token,
        expires_in=86400,
        user_id=user.user_id,
        username=user.username,
        role=user.role,
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    """
    使用refresh_token刷新access_token
    
    刷新成功后旧的refresh_token会失效（防止replay攻击）。
    返回新的access_token和refresh_token对。
    """
    auth = get_auth_manager()
    result = auth.refresh_access_token(request.refresh_token)
    if not result:
        raise HTTPException(status_code=401, detail="Refresh token无效或已过期")
    new_access, new_refresh = result
    return RefreshTokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=86400,
    )


@router.post("/logout")
async def logout(token: str = Depends(_get_token)):
    """
    用户登出
    
    使当前token失效
    """
    auth = get_auth_manager()
    auth.revoke_token(token)
    return APIResponse(message="登出成功")


@router.get("/me", response_model=TokenInfo)
async def get_me(current_user: dict = Depends(_get_current_user)):
    """
    获取当前登录用户信息
    
    需要在Header中携带: Authorization: Bearer <token>
    """
    return TokenInfo(
        user_id=current_user["sub"],
        username=current_user["username"],
        role=current_user["role"],
        exp=current_user["exp"],
    )


@router.post("/register", response_model=APIResponse)
async def register(request: RegisterRequest):
    """
    注册新用户
    
    注意：仅admin角色可注册其他用户
    """
    auth = get_auth_manager()
    try:
        user = auth.register_user(request.username, request.password, request.role)
        return APIResponse(
            data={
                "user_id": user.user_id,
                "username": user.username,
                "role": user.role,
            },
            message="注册成功"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users", response_model=APIResponse)
async def list_users(current_user: dict = Depends(_get_current_user)):
    """
    列出所有用户
    
    仅admin可访问
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要admin权限")
    auth = get_auth_manager()
    return APIResponse(data={"users": auth.list_users()})
