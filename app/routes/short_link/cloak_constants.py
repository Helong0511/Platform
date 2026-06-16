"""
斗篷 / 桥页相关常量。

CLOAK_LOAD_REPORT_INJECT 是一段内联 JavaScript，由服务端在渲染桥页时插入 </body> 之前。
执行时机与逻辑（DOMContentLoaded 后）：

1. 读取 window.__CLOAK_META__（cloak_bridge_html.build_meta_snippet 注入的 base64 JSON）
2. 若 load_report_enabled 为 false，直接退出（不请求 /report）
3. 若 sessionStorage.cloak_load_fb_done 已存在，说明本会话已上报过 load，跳过
4. 从 URL 路径解析短链 short_code（pathname 最后一段，如 /change/abc123 → abc123）
5. 确保 sessionStorage 中有 ad_event_email、ad_event_phone（无则随机生成，供 CAPI 匹配）
6. 从 URL 查询参数取 fbclid，若无则生成 UUID 形态占位符，并写入 ad_event_fbclid 供点击阶段复用
7. 拼接 GET /report?phase=load&fbclid=...&email=...&phone=...&dp=...&report_event=...
8. 请求成功（r.ok）后写入 cloak_load_fb_done，防止同会话重复 load 上报

注意：点击阶段（phase=click）由桥页模板内按钮逻辑触发，不在此脚本内处理。
"""

# 桥页「加载完成」阶段 Facebook 上报脚本（压缩为单行以减小 HTML 体积）
# 依赖：__CLOAK_META__、cloakReportQuerySuffix()（均由 build_meta_snippet 定义）
CLOAK_LOAD_REPORT_INJECT = (
    "<script>(function(){document.addEventListener('DOMContentLoaded',function(){try{"
    "var M=window.__CLOAK_META__||{};if(!M.load_report_enabled)return;"
    "if(sessionStorage.getItem('cloak_load_fb_done'))return;"
    "var segs=location.pathname.split('/').filter(function(x){return x;});"
    "var shortId=segs[segs.length-1]||'';if(!shortId)return;"
    "var email=sessionStorage.getItem('ad_event_email');var phone=sessionStorage.getItem('ad_event_phone');"
    "if(!email){var u=['user','uk_shopper','customer','member','save'];"
    "var d=['gmail.com','outlook.com','yahoo.co.uk','btinternet.com'];"
    "email=u[Math.floor(Math.random()*u.length)]+Math.floor(Math.random()*10000)+'@'+d[Math.floor(Math.random()*d.length)];"
    "sessionStorage.setItem('ad_event_email',email);}"
    "if(!phone){phone=String(Math.floor(7e9+Math.random()*9e9));sessionStorage.setItem('ad_event_phone',phone);}"
    "var fbc=sessionStorage.getItem('ad_event_fbclid');"
    "if(!fbc||!String(fbc).trim()){try{var p=new URLSearchParams(location.search);var f=p.get('fbclid');"
    "if(f&&String(f).trim())fbc=String(f).trim().substring(0,200);}catch(e1){}"
    "if(!fbc||!String(fbc).trim())fbc='xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g,function(c){var r=Math.random()*16|0,v=c==='x'?r:(r&0x3|0x8);return v.toString(16);});"
    "sessionStorage.setItem('ad_event_fbclid',fbc);}else{fbc=String(fbc).trim().substring(0,200);sessionStorage.setItem('ad_event_fbclid',fbc);}"
    "var dpv=(M.dp||'');var qs='id='+encodeURIComponent(shortId)+'&phase=load&fbclid='+encodeURIComponent(fbc)+"
    "'&email='+encodeURIComponent(email)+'&phone='+encodeURIComponent(phone);"
    "if(dpv)qs+='&dp='+encodeURIComponent(dpv);"
    "if(typeof cloakReportQuerySuffix==='function'){qs+=cloakReportQuerySuffix();}"
    "fetch(location.origin+'/report?'+qs,{method:'GET'}).then(function(r){if(r&&r.ok)sessionStorage.setItem('cloak_load_fb_done','1');}).catch(function(){});"
    "}catch(e){}});})();</script>"
)
