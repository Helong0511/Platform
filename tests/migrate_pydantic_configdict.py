"""将 schemas 内 class Config 批量迁移为 model_config = ConfigDict(...)。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "app" / "schemas"

CONFIG_BLOCK = re.compile(
    r"^(\s+)class Config:\n"
    r"\1\s+from_attributes = True\n",
    re.MULTILINE,
)

CONFIG_EXTRA = re.compile(
    r"^(\s+)class Config:\n"
    r"\1\s+extra = \"allow\"\n",
    re.MULTILINE,
)


def ensure_configdict_import(text: str) -> str:
    if "ConfigDict" in text:
        return text
    if re.search(r"from pydantic import (.+)\n", text):
        return re.sub(
            r"from pydantic import ([^\n]+)",
            lambda m: (
                "from pydantic import "
                + (m.group(1) if "ConfigDict" in m.group(1) else m.group(1) + ", ConfigDict")
            ),
            text,
            count=1,
        )
    return "from pydantic import BaseModel, ConfigDict\n" + text


def migrate_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "class Config:" not in text:
        return False
    new = CONFIG_BLOCK.sub(r"\1model_config = ConfigDict(from_attributes=True)\n", text)
    new = CONFIG_EXTRA.sub(r'\1model_config = ConfigDict(extra="allow")\n', new)
    if new == text:
        print(f"skip (unhandled Config): {path.relative_to(ROOT)}")
        return False
    new = ensure_configdict_import(new)
    path.write_text(new, encoding="utf-8")
    print(f"migrated: {path.relative_to(ROOT)}")
    return True


def main() -> int:
    n = 0
    for path in sorted(SCHEMAS.rglob("*.py")):
        if migrate_file(path):
            n += 1
    print(f"total: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
