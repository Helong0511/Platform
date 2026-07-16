"""
斗篷桥页 HTML 加载、元数据注入与 HTTP 响应构建。

本模块是 /change 桥页渲染的核心，将磁盘上的 {cloak_name}.html 模板加工为可投放页面：

1. resolve_bridge_html：按 dp 参数加载 HTML，失败时回退 master.html
2. cloak_meta_from_row：把数据库 CloakConfig 转为前端可用的 __CLOAK_META__ 字典
3. build_meta_snippet / inject_meta_into_html：向 <head> 注入 base64 元数据与 cloakReportQuerySuffix
4. inject_original_url_into_html：替换模板内 getOriginalUrl()，注入服务端算好的跳转 URL
5. append_load_report_inject：在 </body> 前插入加载完成上报脚本（CLOAK_LOAD_REPORT_INJECT）
6. build_bridge_html_response：返回 HTMLResponse，设置 no-cache、CSP、session_id Cookie
"""
import base64
import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

from app.routes.short_link.errors import raise_short_link_not_found
from fastapi.responses import HTMLResponse

from app.core.cloak_scripts_paths import read_bridge_html_template_cached, resolve_bridge_html_read_path
from app.models.models import CloakConfig
from app.routes.short_link.cloak_constants import CLOAK_LOAD_REPORT_INJECT

logger = logging.getLogger(__name__)

# 桥页 HTML 响应的 Content-Security-Policy，限制脚本与资源来源以降低 XSS 风险
BRIDGE_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
    "script-src-attr 'none'; object-src 'none'; "
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
    "img-src 'self' data: https:; font-src 'self' data: https://cdnjs.cloudflare.com; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
    "upgrade-insecure-requests;"
)


def sanitize_dp_param(dp: Optional[str]) -> Optional[str]:
    """过滤 dp 中的非法字符，防止路径遍历；非法时返回 None 走默认 master 桥页。"""
    if dp and not re.match(r"^[a-zA-Z0-9_-]+$", dp):
        logger.debug("[斗篷服务] dp 参数包含非法字符：%s，使用默认桥页", dp)
        return None
    return dp


def resolve_bridge_html(dp: Optional[str]) -> Tuple[str, str, str]:
    """
    加载桥页 HTML。

    Returns:
        (html_content, bridge_page_name, cloak_key)
    """
    dp = sanitize_dp_param(dp)
    bridge_page_name = f"{dp}.html" if dp else "master.html"
    bridge_page_path = resolve_bridge_html_read_path(bridge_page_name)
    if not bridge_page_path and bridge_page_name != "master.html":
        bridge_page_name = "master.html"
        bridge_page_path = resolve_bridge_html_read_path("master.html")
    if not bridge_page_path:
        raise_short_link_not_found("桥页文件不存在")
    html_content = read_bridge_html_template_cached(bridge_page_path)
    cloak_key = (
        bridge_page_name[:-5] if bridge_page_name.endswith(".html") else "master"
    )
    return html_content, bridge_page_name, cloak_key


def cloak_meta_from_row(
        cloak_cfg_row: Optional[CloakConfig],
        cloak_key: str,
) -> Dict[str, Any]:
    """
    将数据库 CloakConfig 行转为注入桥页的 __CLOAK_META__ 字典。

    无配置行时使用点击/加载上报的保守默认值（点击开启、加载关闭）。
    """
    if cloak_cfg_row:
        return {
            "report_event": (cloak_cfg_row.report_event or "ViewContent").strip()
            or "ViewContent",
            "report_value": cloak_cfg_row.report_value,
            "report_currency": (cloak_cfg_row.report_currency or "USD").strip()
            or "USD",
            "dp": cloak_key,
            "click_report_enabled": bool(
                getattr(cloak_cfg_row, "click_report_enabled", True)
            ),
            "load_report_enabled": bool(
                getattr(cloak_cfg_row, "load_report_enabled", False)
            ),
            "load_report_event": (
                getattr(cloak_cfg_row, "load_report_event", None) or "PageView"
            ).strip()
            or "PageView",
            "load_report_value": getattr(cloak_cfg_row, "load_report_value", None),
            "load_report_currency": (
                getattr(cloak_cfg_row, "load_report_currency", None) or "USD"
            ).strip()
            or "USD",
        }
    return {
        "report_event": "ViewContent",
        "report_value": None,
        "report_currency": "USD",
        "dp": cloak_key,
        "click_report_enabled": True,
        "load_report_enabled": False,
        "load_report_event": "PageView",
        "load_report_value": None,
        "load_report_currency": "USD",
    }


def build_meta_snippet(cloak_meta: Dict[str, Any]) -> str:
    """
    生成注入 <head> 的脚本片段：base64 元数据 + 解析为 window.__CLOAK_META__。

    同时定义 cloakReportQuerySuffix()，供桥页点击/加载上报时拼接 report_event 等查询参数。
    """
    meta_b64 = base64.b64encode(
        json.dumps(cloak_meta, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return (
        f'<script type="text/plain" id="cloak-report-meta-b64">{meta_b64}</script>'
        "<script>(function(){try{var t=document.getElementById('cloak-report-meta-b64');"
        "window.__CLOAK_META__=JSON.parse(atob(t.textContent.trim()));}catch(e){"
        "window.__CLOAK_META__={report_event:'ViewContent',report_value:null,report_currency:'USD',"
        "dp:'',click_report_enabled:true,load_report_enabled:false,load_report_event:'PageView',"
        "load_report_value:null,load_report_currency:'USD'};}"
        "window.cloakReportQuerySuffix=function(){var m=window.__CLOAK_META__||{},q='';"
        "if(m.report_event)q+='&report_event='+encodeURIComponent(m.report_event);"
        "if(m.report_event==='Purchase'&&m.report_value!=null&&m.report_value!==''){"
        "q+='&report_value='+encodeURIComponent(String(m.report_value));"
        "q+='&report_currency='+encodeURIComponent(m.report_currency||'USD');}"
        "return q;};})();</script>"
    )


def inject_meta_into_html(html_content: str, meta_snippet: str) -> str:
    """将元数据脚本插入 HTML 的 <head> 内；无 head 标签则 prepend 到全文开头。"""
    if "<head>" in html_content:
        return html_content.replace("<head>", "<head>\n" + meta_snippet + "\n", 1)
    return meta_snippet + "\n" + html_content


def _to_js_string_literal(value: str) -> str:
    """
    将 Python 字符串安全序列化为 JS 字符串字面量（含外层引号）。

    使用 json.dumps，并把 < > & 转为 Unicode 转义，避免在 HTML <script>
    中出现 </script> 等提前闭合标签的序列。
    """
    literal = json.dumps(value if value is not None else "", ensure_ascii=False)
    return (
        literal.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def inject_original_url_into_html(
        html_content: str,
        original_url: str,
        dp: Optional[str],
) -> str:
    """
    替换桥页模板中的 getOriginalUrl() 实现，注入服务端解析后的最终跳转 URL。

    跳转 URL 会附带 email、phone、fbclid、dp 等查询参数（与短链占位符逻辑一致）。
    """
    url_js = _to_js_string_literal(original_url)
    dp_js = _to_js_string_literal(dp or "")
    pattern = r"function getOriginalUrl\([^)]*\) \{[\s\S]*?return originalUrl;[\s\S]*?\}"
    replacement = (
        f'function getOriginalUrl(adEventData) {{ '
        f'let originalUrl = {url_js}; '
        f'const dpParam = {dp_js}; '
        f'const email = adEventData?.email || sessionStorage.getItem("ad_event_email") || ""; '
        f'const phone = adEventData?.phone || sessionStorage.getItem("ad_event_phone") || ""; '
        f'try {{ '
        f'const url = new URL(originalUrl); '
        f'if (email) url.searchParams.set("email", email); '
        f'if (phone) url.searchParams.set("phone", phone); '
        f'const fbclid = getFbclid(); '
        f'if (fbclid) url.searchParams.set("fbclid", fbclid); '
        f'if (dpParam) url.searchParams.set("dp", dpParam); '
        f'originalUrl = url.toString(); '
        f'}} catch (err) {{ '
        f'const fbclid = getFbclid(); '
        f'if (originalUrl.includes("?")) {{ '
        f'if (email) originalUrl += "&email=" + encodeURIComponent(email); '
        f'if (phone) originalUrl += "&phone=" + encodeURIComponent(phone); '
        f'if (fbclid) originalUrl += "&fbclid=" + encodeURIComponent(fbclid); '
        f'if (dpParam) originalUrl += "&dp=" + encodeURIComponent(dpParam); '
        f'}} else {{ '
        f'let params = []; '
        f'if (email) params.push("email=" + encodeURIComponent(email)); '
        f'if (phone) params.push("phone=" + encodeURIComponent(phone)); '
        f'if (fbclid) params.push("fbclid=" + encodeURIComponent(fbclid)); '
        f'if (dpParam) params.push("dp=" + encodeURIComponent(dpParam)); '
        f'if (params.length > 0) originalUrl += "?" + params.join("&"); '
        f'}} '
        f'}} '
        f'return originalUrl; '
        f"}}"
    )
    # 使用回调注入，避免 re.sub 把替换串中的 \u003c 等当作正则转义
    result = re.sub(pattern, lambda _m: replacement, html_content)
    if replacement not in result:
        logger.error("[斗篷服务] 原始URL注入失败")
    return result


def append_load_report_inject(html_content: str) -> str:
    """在 </body> 前插入 CLOAK_LOAD_REPORT_INJECT；无 body 则追加到文末。"""
    if re.search(r"</body\s*>", html_content, flags=re.IGNORECASE):
        return re.sub(
            r"</body\s*>",
            CLOAK_LOAD_REPORT_INJECT + "</body>",
            html_content,
            count=1,
            flags=re.IGNORECASE,
        )
    return html_content + "\n" + CLOAK_LOAD_REPORT_INJECT


def prepare_bridge_html(
        html_content: str,
        cloak_meta: Dict[str, Any],
        original_url: str,
        dp: Optional[str],
) -> str:
    """桥页渲染流水线：注入元数据 → 注入跳转 URL → 注入加载上报脚本。"""
    html_content = inject_meta_into_html(html_content, build_meta_snippet(cloak_meta))
    html_content = inject_original_url_into_html(html_content, original_url, dp)
    return append_load_report_inject(html_content)


def build_bridge_html_response(html_content: str, session_id: str) -> HTMLResponse:
    """
    构造桥页 HTML 响应：禁用缓存、设置 CSP、写入 session_id Cookie（展示次数去重用）。
    """
    response = HTMLResponse(content=html_content)
    response.headers["Content-Security-Policy"] = BRIDGE_CSP
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.set_cookie(
        key="session_id",
        value=session_id,
        max_age=21600,
        path="/",
        domain="client.btfrx.online",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return response
