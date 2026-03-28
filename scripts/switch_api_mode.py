#!/usr/bin/env python3
"""API模式切换脚本

用法:
  python scripts/switch_api_mode.py --mode mock    # 切换到Mock模式
  python scripts/switch_api_mode.py --mode real    # 切换到真实API模式
  python scripts/switch_api_mode.py --status       # 查看当前模式
  python scripts/switch_api_mode.py --config      # 编辑配置
"""
import argparse
import sys
import os
import re
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PROJECT_ROOT, "configs", "config.yaml")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def get_current_mode(config: dict) -> str:
    return config.get("zcloud_api", {}).get("use_mock", True)


def switch_to_mock():
    """切换到Mock模式"""
    config = load_config()
    if "zcloud_api" not in config:
        config["zcloud_api"] = {}
    config["zcloud_api"]["use_mock"] = True
    save_config(config)
    print("✅ 已切换到 Mock 模式")
    print("   - use_mock: true")
    print("   - base_url: http://localhost:18080")


def switch_to_real(
    base_url: str = None,
    api_key: str = None,
    auth_type: str = "api_key",
    oauth_client_id: str = None,
    oauth_client_secret: str = None,
):
    """切换到真实API模式"""
    config = load_config()
    
    # 启用真实API
    if "zcloud_api" not in config:
        config["zcloud_api"] = {}
    config["zcloud_api"]["use_mock"] = False
    
    # 配置真实API参数
    if "zcloud_real_api" not in config:
        config["zcloud_real_api"] = {}
    
    real_api = config["zcloud_real_api"]
    if base_url:
        real_api["base_url"] = base_url
    if api_key:
        real_api["api_key"] = api_key
    real_api["auth_type"] = auth_type
    
    if auth_type == "oauth2":
        if oauth_client_id:
            real_api["oauth_client_id"] = oauth_client_id
        if oauth_client_secret:
            real_api["oauth_client_secret"] = oauth_client_secret
    
    save_config(config)
    
    print("✅ 已切换到 Real API 模式")
    print(f"   - use_mock: false")
    print(f"   - base_url: {real_api.get('base_url')}")
    print(f"   - auth_type: {auth_type}")
    if api_key:
        print(f"   - api_key: {api_key[:8]}***")


def show_status():
    """显示当前模式"""
    config = load_config()
    mode = "Mock" if get_current_mode(config) else "Real API"
    print(f"📌 当前模式: {mode}")
    print()
    print(f"   use_mock = {config.get('zcloud_api', {}).get('use_mock', True)}")
    real_api = config.get("zcloud_real_api", {})
    if real_api:
        print(f"   real_api.base_url = {real_api.get('base_url', 'N/A')}")
        print(f"   real_api.auth_type = {real_api.get('auth_type', 'N/A')}")


def edit_config():
    """交互式编辑配置"""
    import subprocess
    subprocess.run(["vim", CONFIG_FILE])


def main():
    parser = argparse.ArgumentParser(description="zCloud API 模式切换工具")
    parser.add_argument("--mode", choices=["mock", "real"], help="切换到指定模式")
    parser.add_argument("--status", action="store_true", help="查看当前模式")
    parser.add_argument("--config", action="store_true", help="编辑配置文件")
    parser.add_argument("--base-url", help="真实API base_url")
    parser.add_argument("--api-key", help="API Key")
    parser.add_argument("--auth-type", default="api_key", choices=["api_key", "oauth2"], help="认证方式")
    parser.add_argument("--oauth-client-id", help="OAuth2 client_id")
    parser.add_argument("--oauth-client-secret", help="OAuth2 client_secret")
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.config:
        edit_config()
    elif args.mode == "mock":
        switch_to_mock()
    elif args.mode == "real":
        switch_to_real(
            base_url=args.base_url,
            api_key=args.api_key,
            auth_type=args.auth_type,
            oauth_client_id=args.oauth_client_id,
            oauth_client_secret=args.oauth_client_secret,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
