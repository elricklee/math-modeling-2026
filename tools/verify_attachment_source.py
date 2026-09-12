"""核验工作区附件是否来自用户指定的真实目录。

该脚本只读比较文件名、大小和 SHA-256，不修改任何附件；用于防止后续
误把旧缓存或测试数据当作竞赛原始数据。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"D:\数模2026题\C题\附件")
WORKSPACE_COPIES = [
    ROOT / "CUMCM2026Problems" / "C题" / "附件",
    ROOT / "data" / "raw" / "C题",
]
OUTPUT = ROOT / "data" / "processed" / "attachment_source_audit.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(directory: Path) -> dict[str, dict[str, object]]:
    return {
        str(path.relative_to(directory)): {"size": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(directory.rglob("*.xlsx"))
        if not path.name.startswith("~$")
    }


def main() -> int:
    if not SOURCE.exists():
        raise FileNotFoundError(f"真实附件目录不存在：{SOURCE}")
    source = inventory(SOURCE)
    copies = []
    for directory in WORKSPACE_COPIES:
        current = inventory(directory)
        missing = sorted(set(source) - set(current))
        extra = sorted(set(current) - set(source))
        mismatched = sorted(name for name in set(source) & set(current) if source[name] != current[name])
        copies.append({"directory": str(directory), "missing": missing, "extra": extra, "mismatched": mismatched})
    report = {"source": str(SOURCE), "source_files": source, "workspace_copies": copies}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = all(not item["missing"] and not item["extra"] and not item["mismatched"] for item in copies)
    print(f"真实附件文件数：{len(source)}")
    for item in copies:
        status = "PASS" if not item["missing"] and not item["extra"] and not item["mismatched"] else "FAIL"
        print(f"{status} {item['directory']}")
    print(f"审计结果写入：{OUTPUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
