"""Skill 依赖与命名冲突审计。

提取各个 skill 声明的：
  * 调用的工具名（期望它们是本会话可用的工具）
  * 引用的兄弟 skill（期望出现在 skill 目录里）
  * 引用的 references/ 文件（期望真实存在）
然后与本会话实际可用的工具/skill 清单比对，报告缺口。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / ".dsh" / "skills"

# 本会话实际可用的工具（来自会话工具清单，人工登记）
SESSION_TOOLS = {
    # 核心文件
    "read", "write", "edit", "glob", "grep", "read_image", "read_document",
    # 执行
    "pwsh", "workflow", "ralph", "subagent", "subagent_fork",
    "list_subagent_models", "send_message", "interrupt_agent",
    "list_agents", "job_list", "job_output", "job_kill",
    # 目标/规划/交互
    "create_goal", "get_goal", "update_goal", "exit_plan_mode",
    "ask_user_question", "todo_write", "present", "skill",
    # 网络/插件
    "web_search", "web_fetch", "find_dsh_plugin",
    # univer
    "univer_new", "univer_status", "univer_worktree", "univer_unit",
    "univer_import", "univer_execute", "univer_compile_svg", "univer_inspect",
    "univer_lint", "univer_screenshot", "univer_api", "univer_resources",
    "univer_export", "univer_print_pdf",
}

# 本会话可用的 skill（来自 skill 目录）
AVAILABLE_SKILLS = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}

# 这些是"概念性"名字，不是工具/skill，不参与冲突判定
IGNORE = {
    "offset", "limit", "format", "auto", "sheet", "pdf", "DOCX", "XLSX", "TXT",
    "Agg", "TkAgg", "agg", "pdf", "docx", "xlsx", "read", "write", "skill",
}


def extract_backticks(text: str) -> set[str]:
    return set(re.findall(r"`([^`\n]+)`", text))


def main() -> None:
    report: dict = {"per_skill": {}, "missing_tools": {}, "missing_skills": {},
                    "missing_references": {}, "naming_conflicts": []}

    print("=" * 78)
    print("1) 逐 skill 检查")
    for skill_dir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        name = skill_dir.name
        sk = skill_dir / "SKILL.md"
        if not sk.exists():
            report["per_skill"][name] = {"error": "no SKILL.md"}
            continue
        text = sk.read_text(encoding="utf-8")
        tokens = extract_backticks(text)

        # 期望的工具名（形如小写下划线、且在我们登记的工具集合里出现过同形）
        toolish = {t for t in tokens if re.fullmatch(r"[a-z][a-z0-9_]{2,}", t)}
        missing_tools = sorted(t for t in toolish
                               if t not in SESSION_TOOLS
                               and t not in IGNORE
                               and any(k in t for k in ("read", "write", "list", "get",
                                                        "create", "update", "insert",
                                                        "delete", "execute", "inspect")))

        # 引用的 references/ 文件
        refs = set(re.findall(r"references/([A-Za-z0-9._-]+\.md)", text))
        missing_refs = sorted(r for r in refs if not (skill_dir / "references" / r).exists())

        # 引用的兄弟 skill
        mentioned_skills = sorted(s for s in AVAILABLE_SKILLS if s != name and s in text)
        # 形如 "xxx skill" 的引用
        other_skill_refs = set(re.findall(r"`([a-z][a-z0-9-]{3,})`\s+skill", text))
        unknown_skill_refs = sorted(s for s in other_skill_refs
                                    if s not in AVAILABLE_SKILLS and s != name)

        report["per_skill"][name] = {
            "tool_tokens": sorted(toolish),
            "missing_tools": missing_tools,
            "references_found": sorted(refs),
            "missing_references": missing_refs,
            "sibling_skills_present": mentioned_skills,
            "unknown_skill_refs": unknown_skill_refs,
        }
        if missing_tools:
            report["missing_tools"][name] = missing_tools
        if missing_refs:
            report["missing_references"][name] = missing_refs

        print(f"  [{name}]")
        print(f"     缺失工具   : {missing_tools or '无'}")
        print(f"     缺失引用文件: {missing_refs or '无'}")
        print(f"     提到的兄弟 skill: {mentioned_skills or '无'}")

    print("=" * 78)
    print("2) skill 目录命名冲突检查")
    names = sorted(AVAILABLE_SKILLS)
    # 大小写/连字符归一化后是否重复
    norm: dict[str, list[str]] = {}
    for n in names:
        key = n.lower().replace("_", "-")
        norm.setdefault(key, []).append(n)
    dupes = {k: v for k, v in norm.items() if len(v) > 1}
    print(f"   skill 总数: {len(names)}")
    print(f"   归一化后重名: {dupes or '无'}")
    report["naming_conflicts"] = dupes

    # 与全局 profile 里的插件名是否重名（skill 与插件同名会混淆）
    prof_pkg = Path("E:/Deepseek-Harness/deepseek-harness/.dsh/profiles/web/package.json")
    if prof_pkg.exists():
        deps = json.loads(prof_pkg.read_text(encoding="utf-8")).get("dependencies", {})
        overlap = sorted(set(names) & set(deps))
        print(f"   与已装插件同名: {overlap or '无'}")
        report["skill_vs_plugin_overlap"] = overlap

    print("=" * 78)
    print("3) 全局 skill 目录（DSH_HOME）")
    ghome = Path("E:/Deepseek-Harness/deepseek-harness/.dsh/skills")
    print(f"   {ghome} 存在={ghome.exists()}, 条目={list(ghome.iterdir()) if ghome.exists() else '—'}")

    dest = ROOT / "data" / "processed" / "skill_audit.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n明细写入 {dest}")


if __name__ == "__main__":
    main()
