"""在受限沙箱中引导项目依赖（无需 pip 的临时目录）。

背景：本机文件沙箱会拒绝 pip 在临时目录中的 chmod/清理操作，
导致 `pip install` 与 `pip download` 均以 PermissionError 失败。
因此这里自行完成依赖解析与安装：

1. 通过 PyPI JSON API 解析每个包适合当前解释器的 wheel；
2. 递归读取 wheel 内 METADATA 的 Requires-Dist，解析未固定版本的依赖；
3. 用 urllib 下载 wheel 到项目内缓存 `.wheels/`；
4. 用 zipfile 解压到 `.venv/Lib/site-packages`。

用法：
    python tools/bootstrap_env.py                      # 安装 requirements.txt 中的全部包
    python tools/bootstrap_env.py pandas numpy         # 只装指定包（不加版本号即取最新）
    python tools/bootstrap_env.py "numpy==2.5.2"       # 固定版本
"""

from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
import zipfile
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEEL_DIR = ROOT / ".wheels"
SITE_PACKAGES = ROOT / ".venv" / "Lib" / "site-packages"
REQUIREMENTS = ROOT / "requirements.txt"
PYPI_JSON = "https://pypi.org/pypi/{name}/json"

# 这些包在 Windows / 无 GUI 环境下不需要，或会引入不可用的本地依赖
SKIP_PACKAGES = {
    "pywin32", "pywinpty", "pywin32-ctypes",       # Windows GUI / 终端
    "ipykernel", "ipywidgets", "widgetsnbextension",  # notebook GUI 部分
    "jupyter-console", "qtconsole", "qtpy", "pyqt5", "pyqt6", "pyside2", "pyside6",
    "notebook", "nbclassic", "jupyterlab",         # 体积大、与建模无关
    "argon2-cffi", "argon2-cffi-bindings", "notebook-shim",
    "tornado", "pyzmq", "terminado", "send2trash", "websocket-client",
    "prometheus-client", "jupyter-server", "jupyter-server-terminals",
    "jupyter-client", "jupyter-core", "jupyter-events", "jupyter-lsp",
    "jupyterlab-pygments", "jupyterlab-server", "nbclient", "nbconvert",
    "nbformat", "pandocfilters", "bleach", "mistune", "tinycss2", "webencodings",
    "defusedxml", "fastjsonschema", "jsonpointer", "json5", "rfc3339-validator",
    "rfc3986-validator", "uri-template", "webcolors", "isoduration", "fqdn",
    "overrides", "lark", "soupsieve", "beautifulsoup4", "tblib", "stack-data",
    "asttokens", "executing", "pure-eval", "comm", "debugpy", "ipython",
    "ipython-pygments-lexers", "matplotlib-inline", "prompt-toolkit", "ptyprocess",
    "pexpect", "pygments", "wcwidth", "decorator", "appnope", "colorama",
    "anyio", "sniffio", "idna", "certifi", "httpcore", "httpx", "h11",
    "jsonschema", "jsonschema-specifications", "referencing", "rpds-py",
    "attrs", "platformdirs", "traitlets", "nest-asyncio", "async-lru",
    "babel", "charset-normalizer", "requests", "urllib3", "arrow", "python-json-logger",
}

# 无需安装的“环境自带”包
BUILTIN_SKIP = {"python", "pip", "setuptools", "wheel"}

_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_EXTRA_RE = re.compile(r"\[.*?\]")
_PIN_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(==|>=|<=|~=|>|<)?\s*([^\s;]*)")


def log(message: str) -> None:
    print(message, flush=True)


def supported_tags() -> list[str]:
    """当前解释器的 wheel 标签，按优先级从高到低。

    末尾固定追加纯 Python 通用标签：`packaging` 缺失时无法枚举解释器标签，
    此时 `from packaging.tags import sys_tags` 分会退化成单一平台标签，
    导致 `py3-none-any` 之类纯 Python wheel 全部被判为不兼容。
    同时 `wheel_score()` 也会对 `any`/`none` 做通配处理。
    """
    try:
        from packaging.tags import sys_tags
    except ImportError:
        version = f"cp{sys.version_info.major}{sys.version_info.minor}"
        tags = [f"{version}-{version}-win_amd64"]
    else:
        tags = [str(tag) for tag in sys_tags()]
    for universal in ("py3-none-any", "py2.py3-none-any"):
        if universal not in tags:
            tags.append(universal)
    return tags


TAGS: list[str] = []


def wheel_score(filename: str) -> int:
    """wheel 文件名匹配度打分，越高越合适；-1 表示不兼容。"""
    if not filename.endswith(".whl"):
        return -1
    parts = filename[: -len(".whl")].split("-")
    if len(parts) < 5:
        return -1
    py_tag, abi_tag, plat_tag = parts[-3], parts[-2], parts[-1]
    best = -1
    for rank, tag in enumerate(TAGS):
        tag_py, tag_abi, tag_plat = tag.split("-")
        if not _tag_component_matches(tag_plat, plat_tag):
            continue
        if not _tag_component_matches(tag_abi, abi_tag):
            continue
        if not _tag_component_matches(tag_py, py_tag):
            continue
        best = max(best, len(TAGS) - rank)
    return best


def _tag_component_matches(env: str, wheel: str) -> bool:
    """判断 wheel 文件名中的标签分量是否被当前解释器标签分量接受。

    `any`（平台）与 `none`（ABI）是通配值，接受任何解释器标签；
    其余情况按 `.` 分隔的候选项求交集。
    """
    if env == "any" or wheel == "none":
        return True
    return bool(set(env.split(".")) & set(wheel.split(".")))


_META_CACHE: dict[str, dict] = {}


def fetch_meta(name: str) -> dict:
    """取 PyPI 元数据（带缓存）。"""
    key = name.lower()
    if key not in _META_CACHE:
        with urllib.request.urlopen(PYPI_JSON.format(name=name), timeout=60) as resp:
            _META_CACHE[key] = json.load(resp)
    return _META_CACHE[key]


def pick_wheel(name: str, version: str | None = None) -> tuple[str, str, str]:
    """返回 (版本, wheel 文件名, 下载 URL)。"""
    meta = fetch_meta(name)
    resolved = version or meta["info"]["version"]
    releases = meta["releases"].get(resolved)
    if not releases:
        raise LookupError(f"{name}=={resolved} 在 PyPI 上没有发行文件")
    candidates = [(wheel_score(e["filename"]), e["filename"], e["url"])
                  for e in releases if not e.get("yanked")]
    candidates = [c for c in candidates if c[0] >= 0]
    if not candidates:
        raise LookupError(f"{name}=={resolved} 没有兼容当前解释器的 wheel")
    candidates.sort(key=lambda item: (-item[0], item[1]))
    _, filename, url = candidates[0]
    return resolved, filename, url


def download(filename: str, url: str) -> Path:
    WHEEL_DIR.mkdir(parents=True, exist_ok=True)
    dest = WHEEL_DIR / filename
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    with urllib.request.urlopen(url, timeout=600) as resp, dest.open("wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    return dest


def extract(wheel: Path) -> int:
    """解压 wheel 到 site-packages。"""
    SITE_PACKAGES.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(wheel) as zf:
        for info in zf.infolist():
            if info.filename.endswith("/"):
                continue
            if info.filename.endswith((".dist-info/RECORD", ".dist-info/RECORD.jws",
                                       ".dist-info/RECORD.p7s")):
                continue
            target = SITE_PACKAGES / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                dst.write(src.read())
            count += 1
    return count


def requires_from_wheel(wheel: Path) -> list[str]:
    """读取 wheel 内 METADATA 的 Requires-Dist。"""
    with zipfile.ZipFile(wheel) as zf:
        meta_name = next((n for n in zf.namelist() if n.endswith(".dist-info/METADATA")), None)
        if not meta_name:
            return []
        text = zf.read(meta_name).decode("utf-8", "replace")
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("Requires-Dist:"):
            out.append(line.split(":", 1)[1].strip())
        elif not line.strip() and out:
            break
    return out


def parse_requirement(raw: str) -> tuple[str, str | None] | None:
    """把 Requires-Dist 行解析成 (包名, 固定版本或 None)；不适用则返回 None。"""
    if ";" in raw:
        marker = raw.split(";", 1)[1]
        if not marker_applies(marker):
            return None
        raw = raw.split(";", 1)[0]
    raw = _EXTRA_RE.sub("", raw).strip()
    match = _NAME_RE.match(raw)
    if not match:
        return None
    name = match.group(1)
    pin = re.search(r"==\s*([^\s,;]+)", raw)
    version = pin.group(1) if pin else None
    if version and "*" in version:
        version = None
    return name, version


def marker_applies(marker: str) -> bool:
    """粗略判断环境标记是否适用于当前 Windows/py3.13 环境。"""
    marker = marker.lower()
    checks = {
        'sys_platform == "win32"': True,
        'sys_platform == "linux"': False,
        'sys_platform == "darwin"': False,
        'platform_system == "windows"': True,
        'os_name == "nt"': True,
        "extra ==": False,
    }
    for key, value in checks.items():
        if key in marker and not value:
            return False
    for key in ('sys_platform == "linux"', 'sys_platform == "darwin"'):
        if key in marker:
            return False
    if 'python_version' in marker:
        match = re.search(r'python_version\s*([<>=!]+)\s*"([\d.]+)"', marker)
        if match:
            op, want = match.group(1), tuple(int(p) for p in match.group(2).split("."))
            have = sys.version_info[: len(want)]
            ok = {"<": have < want, "<=": have <= want, ">": have > want,
                  ">=": have >= want, "==": have == want, "!=": have != want}.get(op, True)
            return ok and "or" not in marker.replace("python_version", "")
    return True


def read_requirements() -> list[tuple[str, str | None]]:
    if not REQUIREMENTS.exists():
        return []
    out: list[tuple[str, str | None]] = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _PIN_RE.match(line)
        if match:
            out.append((match.group(1), match.group(3) if match.group(2) == "==" else None))
    return out


def install(specs: list[tuple[str, str | None]], with_deps: bool) -> None:
    """按工作队列安装包；每个包解压后继续解析它的依赖。"""
    # 用整体队列 + 已处理集合，保证每个包只尝试一次
    queue: deque[tuple[str, str | None]] = deque(specs)
    handled: set[str] = set()
    ok, failed = 0, 0
    while queue:
        name, version = queue.popleft()
        key = name.lower()
        if key in handled or key in BUILTIN_SKIP or key in SKIP_PACKAGES:
            continue
        handled.add(key)
        log(f"[{len(handled):>3}] {key}{'==' + version if version else ''} ...")
        try:
            resolved, filename, url = pick_wheel(key, version)
            wheel = download(filename, url)
            files = extract(wheel)
            ok += 1
            log(f"      ok  {key}=={resolved}  ({files} 个文件)")
            if with_deps:
                for raw in requires_from_wheel(wheel):
                    parsed = parse_requirement(raw)
                    if parsed:
                        queue.append(parsed)
        except Exception as exc:  # noqa: BLE001 - 引导脚本需要报告全部失败
            failed += 1
            log(f"      !!  {key}: {type(exc).__name__}: {exc}")
    log(f"安装成功 {ok} 个，失败 {failed} 个")


def main(argv: list[str]) -> None:
    global TAGS
    TAGS = supported_tags()
    specs: list[tuple[str, str | None]] = []
    if argv:
        for item in argv:
            match = _PIN_RE.match(item)
            if match:
                specs.append((match.group(1), match.group(3) if match.group(2) == "==" else None))
    else:
        specs = read_requirements()

    log(f"解释器     : {sys.executable}")
    log(f"安装目标   : {SITE_PACKAGES}")
    log(f"wheel 缓存 : {WHEEL_DIR}")
    log(f"计划安装   : {len(specs)} 个顶层包")
    install(specs, with_deps=True)
    log("完成")


if __name__ == "__main__":
    main(sys.argv[1:])
