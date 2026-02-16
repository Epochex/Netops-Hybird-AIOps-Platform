#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path

# ====== 放在仓库根目录运行：/data/Netops-causality-remediation/export.py ======

ROOT_DIR = Path(".").resolve()
OUT_FILE = ROOT_DIR / "code_snapshot.txt"

# 只导出这些后缀（按你这个仓库：Python + Dockerfile + YAML/Conf + Docs + Shell）
ALLOW_EXTS = {
    ".py",
    ".sh", ".bash",
    ".yaml", ".yml",
    ".json",
    ".toml",
    ".ini", ".cfg", ".conf",
    ".md", ".txt",
    ".env",  # 如果你确实希望导出；不想导出可删掉
}

# 一些“无后缀但很关键”的文件名
ALLOW_BASENAMES = {
    "Dockerfile",
    "Makefile",
    "README",
    "LICENSE",
}

# 跳过的目录名（强约束）
SKIP_DIR_NAMES = {
    ".git", ".github",
    "__pycache__", ".pytest_cache", ".mypy_cache",
    ".venv", "venv", ".tox",
    "node_modules",
    "dist", "build", "target",
    ".idea", ".vscode",
    ".DS_Store",
}

# 跳过特定路径前缀（相对 ROOT_DIR）
SKIP_REL_PREFIXES = {
    Path("edge") / "fortigate-ingest" / "bin" / "__pycache__",
}

# 单文件最大读取大小（防止把大日志/大模型/大二进制扫进去）
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2MB


def should_skip_dir(dirpath: Path) -> bool:
    name = dirpath.name
    if name in SKIP_DIR_NAMES:
        return True
    return False


def is_allowed_file(p: Path) -> bool:
    # 跳过明显的二进制/缓存
    if p.name.endswith((".pyc", ".pyo")):
        return False

    # 无后缀但关键的文件
    if p.suffix == "" and p.name in ALLOW_BASENAMES:
        return True

    # 有后缀白名单
    if p.suffix.lower() in ALLOW_EXTS:
        return True

    # 允许 Dockerfile.* / *.service / *.timer 等“重要但不在白名单后缀里”的场景
    if p.name.startswith("Dockerfile"):
        return True

    return False


def is_under_skipped_prefix(rel: Path) -> bool:
    for pref in SKIP_REL_PREFIXES:
        try:
            rel.relative_to(pref)
            return True
        except ValueError:
            pass
    return False


def safe_read_text(file_path: Path) -> str:
    # 先按 utf-8，失败再 latin-1，避免直接崩
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return file_path.read_text(encoding="latin-1", errors="replace")


def build_tree_preview(root: Path) -> str:
    # 简易 tree（不依赖系统 tree 命令）
    lines = []
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        rel_dp = dp.relative_to(root)

        # 过滤目录
        dirnames[:] = [d for d in dirnames if not should_skip_dir(Path(d))]
        # 过滤前缀目录（rel 前缀）
        if rel_dp != Path(".") and is_under_skipped_prefix(rel_dp):
            dirnames[:] = []
            continue

        indent = "  " * (len(rel_dp.parts) - (0 if rel_dp == Path(".") else 0))
        # 根目录不打印 "."
        if rel_dp != Path("."):
            lines.append(f"{indent}{rel_dp.name}/")

        # 文件
        for fn in sorted(filenames):
            p = dp / fn
            rel = p.relative_to(root)
            if is_under_skipped_prefix(rel.parent):
                continue
            if is_allowed_file(p):
                lines.append(f"{indent}  {fn}")

    return "\n".join(lines) + "\n"


def main():
    collected = []

    for dirpath, dirnames, filenames in os.walk(ROOT_DIR):
        dp = Path(dirpath)
        rel_dp = dp.relative_to(ROOT_DIR)

        # 跳过目录名
        dirnames[:] = [d for d in dirnames if not should_skip_dir(Path(d))]
        # 跳过前缀路径
        if rel_dp != Path(".") and is_under_skipped_prefix(rel_dp):
            dirnames[:] = []
            continue

        for fn in filenames:
            p = dp / fn
            rel = p.relative_to(ROOT_DIR)

            if is_under_skipped_prefix(rel.parent):
                continue
            if not is_allowed_file(p):
                continue

            # 跳过超大文件
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > MAX_FILE_BYTES:
                continue

            collected.append((str(rel), p))

    collected.sort(key=lambda x: x[0])

    with OUT_FILE.open("w", encoding="utf-8") as out:
        out.write("# Netops-causality-remediation code snapshot\n")
        out.write(f"# Root: {ROOT_DIR}\n")
        out.write(f"# Files: {len(collected)}\n\n")

        out.write("## TREE (filtered)\n")
        out.write(build_tree_preview(ROOT_DIR))
        out.write("\n\n")

        for rel, p in collected:
            out.write("=" * 100 + "\n")
            out.write(f"FILE: {rel}\n")
            out.write("=" * 100 + "\n")
            out.write(safe_read_text(p))
            if not safe_read_text(p).endswith("\n"):
                out.write("\n")
            out.write("\n")

    print(f"[OK] Exported {len(collected)} files -> {OUT_FILE}")


if __name__ == "__main__":
    main()

