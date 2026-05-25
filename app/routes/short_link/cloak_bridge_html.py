"""斗篷桥页 HTML 加载、元数据注入与响应构建。"""
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

BRIDGE_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
    "img-src 'self' data: https:; font-src 'self' data: https://cdnjs.cloudflare.com; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; "
    "upgrade-insecure-requests;"
)


def sanitize_dp_param(dp: Optional[str]) -> Optional[str]:
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
    if "<head>" in html_content:
        return html_content.replace("<head>", "<head>\n" + meta_snippet + "\n", 1)
    return meta_snippet + "\n" + html_content


def inject_original_url_into_html(
        html_content: str,
        original_url: str,
        dp: Optional[str],
) -> str:
    escaped_url = original_url.replace("\\", "\\\\").replace('"', '\\"')
    escaped_dp = (dp or "").replace("\\", "\\\\").replace('"', '\\"')
    pattern = r"function getOriginalUrl\([^)]*\) \{[\s\S]*?return originalUrl;[\s\S]*?\}"
    replacement = (
        f'function getOriginalUrl(adEventData) {{ '
        f'let originalUrl = "{escaped_url}"; '
        f'const dpParam = "{escaped_dp}"; '
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
    result = re.sub(pattern, replacement, html_content)
    if replacement not in result:
        logger.error("[斗篷服务] 原始URL注入失败")
    return result


def append_load_report_inject(html_content: str) -> str:
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
    html_content = inject_meta_into_html(html_content, build_meta_snippet(cloak_meta))
    html_content = inject_original_url_into_html(html_content, original_url, dp)
    return append_load_report_inject(html_content)


def build_bridge_html_response(html_content: str, session_id: str) -> HTMLResponse:
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
