"""认证模块 - JWT Token用户认证系统"""
import os
import time
import json
import secrets
import hashlib
import hmac
from typing import Optional
from dataclasses import dataclass
from pathlib import Path


def _get_data_dir() -> Path:
    """获取数据目录路径"""
    return Path(os.environ.get("DATA_DIR", "data"))


def _get_users_file() -> Path:
    """获取用户文件路径"""
    return _get_data_dir() / "users.json"


def _get_secret_file() -> Path:
    """获取密钥文件路径"""
    return _get_data_dir() / "auth_secret.key"


def _get_secret(secret_file: Optional[Path] = None) -> str:
    """获取或生成JWT密钥"""
    secret_file = secret_file or _get_secret_file()
    if secret_file.exists():
        return secret_file.read_text().strip()
    secret = secrets.token_hex(32)
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    secret_file.write_text(secret)
    os.chmod(str(secret_file), 0o600)
    return secret


def _load_users(users_file: Optional[Path] = None) -> dict:
    users_file = users_file or _get_users_file()
    if not users_file.exists():
        return {}
    with open(users_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(users: dict, users_file: Optional[Path] = None):
    users_file = users_file or _get_users_file()
    users_file.parent.mkdir(parents=True, exist_ok=True)
    with open(users_file, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """哈希密码，返回 (hash, salt)"""
    if salt is None:
        salt = secrets.token_hex(16)
    combined = f"{salt}:{password}"
    for _ in range(100_000):
        combined = hashlib.sha256(combined.encode()).hexdigest()
    return combined, salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """验证密码"""
    computed, _ = hash_password(password, salt)
    return hmac.compare_digest(computed, hashed)


@dataclass
class User:
    user_id: str
    username: str
    password_hash: str
    password_salt: str
    role: str = "user"
    created_at: float = 0
    is_active: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> "User":
        return cls(
            user_id=d["user_id"],
            username=d["username"],
            password_hash=d["password_hash"],
            password_salt=d["password_salt"],
            role=d.get("role", "user"),
            created_at=d.get("created_at", 0),
            is_active=d.get("is_active", True),
        )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "password_hash": self.password_hash,
            "password_salt": self.password_salt,
            "role": self.role,
            "created_at": self.created_at,
            "is_active": self.is_active,
        }


class AuthManager:
    """认证管理器"""

    def __init__(self, users_file: Optional[Path] = None, secret_file: Optional[Path] = None):
        self._users_file = users_file or _get_users_file()
        self._secret_file = secret_file or _get_secret_file()
        self._secret = _get_secret(self._secret_file)
        self._token_file = _get_data_dir() / "tokens.json"
        self._tokens: dict = {}  # token -> {user_id, expires_at, revoked: bool}
        self._revoked: set = set()  # 已撤销的jti集合
        self._load_tokens()

    def _load_tokens(self):
        if self._token_file.exists():
            with open(self._token_file, "r") as f:
                data = json.load(f)
                self._tokens = data.get("tokens", {})
                self._revoked = set(data.get("revoked", []))

    def _save_tokens(self):
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._token_file, "w") as f:
            json.dump({"tokens": self._tokens, "revoked": list(self._revoked)}, f)

    def register_user(self, username: str, password: str, role: str = "user") -> User:
        """注册用户"""
        users = _load_users(self._users_file)
        # 检查用户名唯一
        for u in users.values():
            if u["username"] == username:
                raise ValueError(f"用户名已存在: {username}")
        import uuid
        user_id = str(uuid.uuid4())[:8]
        pw_hash, salt = hash_password(password)
        user = User(
            user_id=user_id,
            username=username,
            password_hash=pw_hash,
            password_salt=salt,
            role=role,
            created_at=time.time(),
        )
        users[user_id] = user.to_dict()
        _save_users(users, self._users_file)
        return user

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """验证用户名密码"""
        users = _load_users(self._users_file)
        for u in users.values():
            if u["username"] == username and u["is_active"]:
                user = User.from_dict(u)
                if verify_password(password, user.password_hash, user.password_salt):
                    return user
        return None

    def create_token(self, user: User, expires_in: int = 86400, token_type: str = "access") -> tuple[str, Optional[str]]:
        """
        创建JWT token
        
        Args:
            user: 用户对象
            expires_in: 有效期（秒），默认24小时
            token_type: token类型，"access"或"refresh"
        
        Returns:
            tuple: (access_token, refresh_token)
                   access_token有效期24小时
                   refresh_token有效期7天
        """
        import jwt
        now = time.time()
        
        # 确保用户已注册（如果不存在则添加）
        users = _load_users(self._users_file)
        if user.user_id not in users:
            users[user.user_id] = user.to_dict()
            _save_users(users, self._users_file)
        
        # Access Token
        access_payload = {
            "sub": user.user_id,
            "username": user.username,
            "role": user.role,
            "iat": now,
            "exp": now + expires_in,
            "jti": secrets.token_hex(16),
            "type": "access",
        }
        access_token = jwt.encode(access_payload, self._secret, algorithm="HS256")
        
        # Refresh Token（有效期7天）
        refresh_payload = {
            "sub": user.user_id,
            "username": user.username,
            "iat": now,
            "exp": now + (7 * 86400),
            "jti": secrets.token_hex(16),
            "type": "refresh",
        }
        refresh_token = jwt.encode(refresh_payload, self._secret, algorithm="HS256")
        
        # 存储到本地token列表（用于登出/失效）
        self._tokens[access_token] = {
            "user_id": user.user_id,
            "expires_at": access_payload["exp"],
            "type": "access",
        }
        self._tokens[refresh_token] = {
            "user_id": user.user_id,
            "expires_at": refresh_payload["exp"],
            "type": "refresh",
        }
        self._save_tokens()
        return access_token, refresh_token
    
    def refresh_access_token(self, refresh_token: str) -> Optional[tuple[str, str]]:
        """
        使用refresh_token刷新access_token
        
        Returns:
            tuple: (new_access_token, new_refresh_token) 或 None（刷新失败）
        """
        import jwt
        try:
            payload = jwt.decode(refresh_token, self._secret, algorithms=["HS256"], options={"verify_exp": False})
        except jwt.InvalidTokenError:
            return None
        
        # 验证是refresh token
        if payload.get("type") != "refresh":
            return None
        
        # 检查是否已撤销
        jti = payload.get("jti")
        if jti and jti in self._revoked:
            return None
        
        # 检查是否过期
        exp = payload.get("exp", 0)
        if exp < time.time():
            return None
        
        # 获取用户
        user_id = payload.get("sub")
        user = self.get_user(user_id)
        if not user:
            return None
        
        # 作废旧refresh token（防止replay attack）
        if jti:
            self._revoked.add(jti)
        if refresh_token in self._tokens:
            del self._tokens[refresh_token]
        
        # 生成新token对
        return self.create_token(user, expires_in=86400)

    def verify_token(self, token: str, require_type: Optional[str] = "access") -> Optional[dict]:
        """
        验证并解析JWT token
        
        Args:
            token: JWT token字符串
            require_type: 要求的token类型，"access"/"refresh"/None（不限制）
        """
        import jwt
        # 解码以获取jti（不验证exp，因为我们自己检查）
        try:
            payload = jwt.decode(token, self._secret, algorithms=["HS256"], options={"verify_exp": False})
        except jwt.InvalidTokenError:
            return None

        jti = payload.get("jti")
        # 检查是否已撤销
        if jti and jti in self._revoked:
            return None

        # 检查是否过期
        exp = payload.get("exp", 0)
        if exp < time.time():
            return None
        
        # 检查token类型
        if require_type and payload.get("type") != require_type:
            return None

        return payload

    def revoke_token(self, token: str):
        """撤销token（登出）"""
        # 获取jti以便追踪
        try:
            import jwt
            payload = jwt.decode(token, self._secret, algorithms=["HS256"], options={"verify_exp": False})
            jti = payload.get("jti")
            if jti:
                self._revoked.add(jti)
        except Exception:
            pass
        # 从有效token列表移除
        if token in self._tokens:
            del self._tokens[token]
        self._save_tokens()

    def get_user(self, user_id: str) -> Optional[User]:
        """根据user_id获取用户"""
        users = _load_users(self._users_file)
        if user_id in users:
            return User.from_dict(users[user_id])
        return None

    def list_users(self) -> list[dict]:
        """列出所有用户（不含密码）"""
        users = _load_users(self._users_file)
        return [
            {
                "user_id": u["user_id"],
                "username": u["username"],
                "role": u["role"],
                "created_at": u["created_at"],
                "is_active": u["is_active"],
            }
            for u in users.values()
        ]

    # 确保默认admin账户存在
    def ensure_admin(self, admin_password: str = "admin123"):
        """确保存在admin账户"""
        users = _load_users(self._users_file)
        for u in users.values():
            if u["role"] == "admin":
                return
        self.register_user("admin", admin_password, role="admin")


_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
        _auth_manager.ensure_admin()
    return _auth_manager
