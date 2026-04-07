#!/usr/bin/env python3
"""
简单的PDF生成测试脚本
"""

import subprocess
import os
import sys

# 切换到技能目录
os.chdir("/Users/lihuan/python-workspace/Aix-DB/agent/common/skills/minimax-pdf")

# 使用系统Python执行各个步骤
print("步骤1: 生成设计令牌...")
result1 = subprocess.run([
    "/usr/bin/python3", "scripts/palette.py",
    "--title", "PDF测试文档",
    "--type", "report",
    "--author", "AI助手",
    "--date", "2024年",
    "--accent", "#2D5F8A",
    "--out", "tokens.json"
], capture_output=True, text=True)
print(result1.stdout)
if result1.returncode != 0:
    print("错误:", result1.stderr)
    sys.exit(1)

print("\n步骤2: 渲染正文...")
# 直接调用render_body.py，跳过依赖检查
result2 = subprocess.run([
    "/usr/bin/python3", "-c",
    """
import sys
sys.path.insert(0, '.')
from scripts.render_body import main
sys.argv = ['render_body.py', '--tokens', 'tokens.json', '--content', 'test_content.json', '--out', 'body.pdf']
main()
    """
], capture_output=True, text=True)
print(result2.stdout)
if result2.returncode != 0:
    print("错误:", result2.stderr)
    # 尝试直接运行脚本
    print("\n尝试直接运行脚本...")
    result2b = subprocess.run([
        "/usr/bin/python3", "scripts/render_body.py",
        "--tokens", "tokens.json",
        "--content", "test_content.json",
        "--out", "body.pdf"
    ], capture_output=True, text=True)
    print(result2b.stdout)
    if result2b.returncode != 0:
        print("错误:", result2b.stderr)

print("\n完成!")