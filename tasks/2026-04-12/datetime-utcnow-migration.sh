#!/bin/bash
# datetime.utcnow() 迁移脚本
# Python 3.12+ deprecated: datetime.utcnow() → datetime.now(timezone.utc)
# 
# 使用方法: bash datetime-utcnow-migration.sh <project_path>
#
# 2026-04-12 | 真理

PROJECT_PATH="${1:-.}"

echo "=== datetime.utcnow() 迁移检查 ==="
echo "项目路径: $PROJECT_PATH"
echo ""

# 1. 查找所有使用 utcnow() 的文件
echo ">>> 扫描 utcnow() 使用..."
UTCNOW_FILES=$(grep -rln "utcnow()" "$PROJECT_PATH" --include="*.py" 2>/dev/null || true)

if [ -z "$UTCNOW_FILES" ]; then
    echo "✅ 未发现 utcnow() 使用"
    exit 0
fi

echo "发现以下文件使用 utcnow():"
echo "$UTCNOW_FILES"
echo ""

# 2. 生成修复脚本
MIGRATION_SCRIPT="/tmp/fix_utcnow.py"
echo ">>> 生成修复脚本: $MIGRATION_SCRIPT"

cat > "$MIGRATION_SCRIPT" << 'SCRIPT'
import re
import sys

# 迁移规则:
# datetime.utcnow() → datetime.now(timezone.utc)
# datetime.utcfromtimestamp() → datetime.fromtimestamp(ts, tz=timezone.utc)

REPLACEMENTS = [
    (r'datetime\.utcnow\(\)', 'datetime.now(timezone.utc)'),
    (r'datetime\.utcfromtimestamp\(', 'datetime.fromtimestamp(',  # 需要额外处理
]

def fix_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    original = content
    
    # 修复 datetime.utcnow()
    content = re.sub(
        r'datetime\.utcnow\(\)',
        'datetime.now(timezone.utc)',
        content
    )
    
    # 添加 import (如果还没有 timezone)
    if 'timezone.utc' in content and 'from datetime import' in content:
        if 'timezone' not in content:
            content = re.sub(
                r'(from datetime import\s+)(.*?)(?=\n|$)',
                r'\1\2, timezone',
                content
            )
    
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        return True
    return False

if __name__ == '__main__':
    for filepath in sys.argv[1:]:
        if fix_file(filepath):
            print(f"Fixed: {filepath}")
        else:
            print(f"No changes: {filepath}")
SCRIPT

# 3. 执行修复 (预览模式)
echo ""
echo ">>> 预览修复 (dry-run)..."
for file in $UTCNOW_FILES; do
    echo "--- $file ---"
    grep -n "utcnow()" "$file" || true
done

echo ""
read -p "是否执行修复? (y/N): " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    python3 "$MIGRATION_SCRIPT" $UTCNOW_FILES
    echo "✅ 修复完成"
else
    echo "❌ 已取消"
fi
