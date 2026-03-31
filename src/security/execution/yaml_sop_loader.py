"""YAML SOP 加载器

从 `knowledge/sop_yaml/` 目录加载结构化 YAML SOP 文件，
转换为 SOPExecutor 可以直接使用的 dict 格式。

YAML 格式参考：道衍设计文档 V2.0 Round 1 方案B。

使用方式：
    loader = YAMLSOPLoader()
    sops = loader.load_all()
    loader.load_one("slow_sql_diagnosis")
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# 目录配置
# ---------------------------------------------------------------------------

# 默认 YAML SOP 目录（相对于项目根目录）
_DEFAULT_SOP_YAML_DIR = "knowledge/sop_yaml/"


def _resolve_project_root() -> str:
    """解析项目根目录（src/ 上两级）"""
    # __file__ = Javis-DB-Agent/src/security/execution/yaml_sop_loader.py
    return str(Path(__file__).resolve().parent.parent.parent.parent)


def _get_default_sop_dir() -> str:
    """获取默认 SOP YAML 目录的绝对路径"""
    root = _resolve_project_root()
    default_dir = os.environ.get("JAVIS_SOP_YAML_DIR", "")
    if default_dir:
        return default_dir
    return os.path.join(root, _DEFAULT_SOP_YAML_DIR)


# ---------------------------------------------------------------------------
# 加载器实现
# ---------------------------------------------------------------------------

class YAMLSOPLoader:
    """
    YAML SOP 加载器

    负责：
    - 从指定目录加载所有 .yaml / .yml 文件
    - 单个文件加载
    - SOP dict 规范化（兼容 SOPExecutor 期望的字段）
    """

    def __init__(self, sop_dir: Optional[str] = None):
        """
        Args:
            sop_dir: YAML SOP 文件目录，默认为 `knowledge/sop_yaml/`
        """
        self.sop_dir = sop_dir or _get_default_sop_dir()

    def load_all(self) -> Dict[str, dict]:
        """
        加载目录下所有 YAML SOP 文件。

        Returns:
            {sop_id: sop_dict} 字典
        """
        sops = {}
        dir_path = Path(self.sop_dir)

        if not dir_path.exists():
            return sops

        for filepath in dir_path.glob("*.yaml"):
            sop = self._load_file(filepath)
            if sop:
                sop_id = sop.get("id") or sop.get("sop_id") or sop.get("name", "")
                if sop_id:
                    sops[sop_id] = sop

        # 也支持 .yml 扩展名
        for filepath in dir_path.glob("*.yml"):
            if filepath.suffix == ".yml":
                sop = self._load_file(filepath)
                if sop:
                    sop_id = sop.get("id") or sop.get("sop_id") or sop.get("name", "")
                    if sop_id:
                        sops[sop_id] = sop

        return sops

    def load_one(self, sop_id: str) -> Optional[dict]:
        """
        加载指定的单个 SOP。

        Args:
            sop_id: SOP ID（即文件名，不含扩展名）

        Returns:
            SOP dict，文件不存在时返回 None
        """
        dir_path = Path(self.sop_dir)

        for ext in (".yaml", ".yml"):
            filepath = dir_path / f"{sop_id}{ext}"
            if filepath.exists():
                return self._load_file(filepath)

        return None

    def _load_file(self, filepath: Path) -> Optional[dict]:
        """
        加载并规范化单个 YAML 文件。

        Args:
            filepath: YAML 文件路径

        Returns:
            规范化后的 SOP dict，解析失败时返回 None
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)

            if not raw:
                return None

            return self._normalize(raw)

        except (yaml.YAMLError, OSError) as e:
            # 解析失败时记录并跳过（不中断其他文件）
            print(f"[YAMLSOPLoader] 加载失败 {filepath}: {e}")
            return None

    def _sanitize_id(self, name: str) -> str:
        """将name转换为合法的id（字母数字下划线）"""
        import re
        return re.sub(r"[^a-zA-Z0-9_]", "_", name)

    def _normalize(self, raw: dict) -> dict:
        """
        将 YAML dict 规范化为 SOPExecutor 期望的格式。

        规范化规则：
        - sop_id / id / name 统一映射到 id
        - step_id / id / step 统一映射到 step id
        - steps[].step_id 补全为数字（兼容旧格式）
        - risk_level 统一为整数
        - timeout_seconds 默认 60
        """
        sop = dict(raw)

        # id 字段（必填）- sop_id / id / name 统一
        sop["id"] = sop.get("id") or sop.get("sop_id") or self._sanitize_id(sop.get("name", ""))

        # steps 规范化
        steps = sop.get("steps", [])
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                continue

            # step id 统一：step_id / id / step -> id
            step["id"] = step.get("id") or step.get("step_id") or f"step_{i}"

            # 补全 step 序号（兼容 "step_id" 和 "step" 两种格式）
            if "step" not in step and "step_id" not in step:
                step["step"] = i + 1

            # risk_level 统一为整数
            rl = step.get("risk_level", 1)
            if isinstance(rl, str):
                rl = int(rl.lstrip("Ll"))
            step["risk_level"] = int(rl)

            # timeout_seconds 默认值
            if "timeout_seconds" not in step:
                step["timeout_seconds"] = 60

            # description / name 兼容
            if "description" not in step:
                step["description"] = step.get("name", step.get("action", ""))

        sop["steps"] = steps

        # 全局 risk_level
        if "risk_level" in sop:
            rl = sop["risk_level"]
            if isinstance(rl, str):
                rl = int(rl.lstrip("Ll"))
            sop["risk_level"] = int(rl)

        # 全局 timeout_seconds
        if "timeout_seconds" not in sop:
            sop["timeout_seconds"] = 300

        return sop


# ---------------------------------------------------------------------------
# 便捷入口（可选，用于命令行测试）
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = YAMLSOPLoader()
    sops = loader.load_all()
    print(f"[YAMLSOPLoader] 加载了 {len(sops)} 个 SOP:")
    for sid, sop in sops.items():
        print(f"  - {sid}: {sop.get('name', '')} ({len(sop.get('steps', []))} steps)")
