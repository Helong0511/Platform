"""
桥页 HTML 上传消毒。

管理端上传的 {cloak_name}.html 会经公开 /change 下发给访客，须在上传时剔除常见 XSS 载体，
同时保留桥页业务所需的 inline script/style、CDN 样式与 data:image 图标。
"""
from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 整棵移除（含子节点与文本）
_DROP_TAGS = frozenset(
    {
        "iframe",
        "frame",
        "frameset",
        "object",
        "embed",
        "applet",
        "base",
        "template",
        "svg",
        "math",
    }
)

# 允许保留的 link rel（桥页常用 stylesheet / icon）
_ALLOWED_LINK_RELS = frozenset({"stylesheet", "icon", "shortcut icon", "apple-touch-icon"})

# href/src/action 等 URL 属性
_URL_ATTRS = frozenset({"href", "src", "action", "formaction", "poster", "background", "data"})

# 任意标签上禁止保留的属性
_STRIP_ATTRS = frozenset({"srcdoc", "xmlns", "xlink:href"})

# meta http-equiv 禁止值
_FORBIDDEN_META_HTTP_EQUIV = frozenset({"refresh", "set-cookie", "content-security-policy"})

# inline style 危险片段
_DANGEROUS_STYLE = re.compile(
    r"expression\s*\(|javascript\s*:|vbscript\s*:|behavior\s*:|@import|url\s*\(\s*['\"]?\s*javascript:",
    re.IGNORECASE,
)


def _attr_map(attrs: List[Tuple[str, Optional[str]]]) -> Dict[str, Optional[str]]:
    return {k.lower(): v for k, v in attrs}


def _is_safe_bridge_url(url: Optional[str]) -> bool:
    """桥页 URL 白名单：相对路径、http(s)、data:image/*。"""
    if url is None:
        return True
    raw = url.strip()
    if not raw:
        return True

    lower = raw.lower()
    if lower.startswith(("javascript:", "vbscript:", "livescript:")):
        return False
    if re.match(r"javascript\s*:", lower):
        return False

    if lower.startswith("data:"):
        return lower.startswith("data:image/")

    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https"):
        return True
    if parsed.scheme == "":
        # 相对路径、锚点、查询串
        if raw.startswith(("#", "?", "/")) or not parsed.scheme:
            return True
        return False

    return False


class _BridgeHtmlSanitizer(HTMLParser):
    """基于 html.parser 的桥页 HTML 消毒器。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._parts: List[str] = []
        self._skip_stack: List[str] = []
        self._removed: List[str] = []

    @property
    def removed_notes(self) -> List[str]:
        return self._removed

    def get_html(self) -> str:
        return "".join(self._parts)

    def _note(self, msg: str) -> None:
        self._removed.append(msg)
        logger.warning("桥页 HTML 消毒移除: %s", msg)

    def _emit(self, text: str) -> None:
        if not self._skip_stack:
            self._parts.append(text)

    def _should_skip(self) -> bool:
        return bool(self._skip_stack)

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        name = tag.lower()
        amap = _attr_map(attrs)

        if self._should_skip():
            return

        if name == "link":
            if not self._link_allowed(amap):
                self._note(f"不允许的 <link> rel={amap.get('rel')!r}")
            else:
                self._emit_startend(name, attrs)
            return

        if name in _DROP_TAGS:
            self._note(f"危险标签 <{name}>")
            self._skip_stack.append(name)
            return

        if name == "script":
            if amap.get("src"):
                self._note("外链 <script src=...>")
                self._skip_stack.append(name)
                return

        if name == "meta":
            http_equiv = (amap.get("http-equiv") or "").strip().lower()
            if http_equiv in _FORBIDDEN_META_HTTP_EQUIV:
                self._note(f"危险 <meta http-equiv={http_equiv!r}>")
                return

        self._emit_startend(name, attrs)

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self._emit_startend(tag.lower(), attrs)

    def _emit_startend(self, name: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if self._should_skip():
            return

        if name == "link":
            amap = _attr_map(attrs)
            if not self._link_allowed(amap):
                self._note(f"不允许的 <link> rel={amap.get('rel')!r}")
                return

        if name in _DROP_TAGS:
            self._note(f"危险标签 <{name}>")
            return

        if name == "script" and _attr_map(attrs).get("src"):
            self._note("外链 <script src=...>")
            return

        clean_attrs = self._clean_attrs(name, attrs)
        attr_str = "".join(
            f' {k}' if v is None else f' {k}="{self._escape_attr(v)}"'
            for k, v in clean_attrs
        )
        self._emit(f"<{name}{attr_str}>")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if self._skip_stack and name == self._skip_stack[-1]:
            self._skip_stack.pop()
            return
        if self._should_skip():
            return
        self._emit(f"</{name}>")

    def handle_data(self, data: str) -> None:
        if not self._should_skip():
            self._emit(data)

    def handle_comment(self, data: str) -> None:
        # 去掉 HTML 注释，避免 IE 条件注释等隐藏 payload
        if data.strip():
            self._note("HTML 注释")

    def handle_decl(self, decl: str) -> None:
        self._emit(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._note("处理指令 <?...?>")

    @staticmethod
    def _escape_attr(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
        )

    def _link_allowed(self, amap: Dict[str, Optional[str]]) -> bool:
        rel = (amap.get("rel") or "stylesheet").strip().lower()
        if rel not in _ALLOWED_LINK_RELS:
            return False
        href = amap.get("href")
        if href and not _is_safe_bridge_url(href):
            return False
        return True

    def _clean_attrs(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]]
    ) -> List[Tuple[str, Optional[str]]]:
        cleaned: List[Tuple[str, Optional[str]]] = []
        for key, value in attrs:
            lower = key.lower()
            if lower in _STRIP_ATTRS or lower.startswith("on"):
                self._note(f"危险属性 {tag}.{lower}")
                continue
            if lower == "style" and value and _DANGEROUS_STYLE.search(value):
                self._note(f"危险 style 属性 ({tag})")
                continue
            if lower in _URL_ATTRS and value is not None and not _is_safe_bridge_url(value):
                self._note(f"危险 URL 属性 {tag}.{lower}")
                continue
            cleaned.append((key, value))
        return cleaned


def sanitize_bridge_html(html: str) -> Tuple[str, List[str]]:
    """
    消毒桥页 HTML，返回 (净化后文本, 移除项说明列表)。

    若解析失败则抛出 ValueError。
    """
    parser = _BridgeHtmlSanitizer()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise ValueError(f"HTML 解析失败，无法消毒：{exc}") from exc

    sanitized = parser.get_html()
    notes = parser.removed_notes
    if notes:
        logger.info("桥页 HTML 消毒完成，移除 %d 项", len(notes))
    return sanitized, notes


def sanitize_bridge_html_strict(html: str) -> str:
    """
    消毒桥页 HTML；若发现需移除的危险内容则拒绝上传。

    Raises:
        ValueError: 存在 iframe/外链 script/事件属性等不可接受内容
    """
    sanitized, notes = sanitize_bridge_html(html)
    if notes:
        preview = "；".join(notes[:5])
        extra = f" 等共 {len(notes)} 项" if len(notes) > 5 else ""
        raise ValueError(
            f"HTML 含不允许的内容（{preview}{extra}）。"
            "请移除 iframe、外链 script、事件属性(onclick 等)、javascript: 链接后重新上传。"
        )
    return sanitized
