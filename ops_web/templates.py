"""Embedded HTML templates for the web console.

Uses Python string concatenation — no Jinja2 dependency needed.
JS code is kept in separate variables to avoid f-string {{}} escaping issues.
"""

STYLE = """
  :root {
    --bg: #1a1a2e; --surface: #16213e; --text: #e0e0e0;
    --accent: #00d2ff; --ok: #27ae60; --warn: #f39c12; --crit: #e74c3c;
    --muted: #7f8c8d; --border: #2c3e50;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'SF Mono','Cascadia Code','Consolas',monospace;
         background: var(--bg); color: var(--text); line-height: 1.5; }
  nav { background: var(--surface); padding: 0.75rem 1.5rem;
        border-bottom: 1px solid var(--border); display: flex; gap: 1.5rem; }
  nav a { color: var(--accent); text-decoration: none; font-weight: 600; }
  nav a:hover { text-decoration: underline; }
  main { max-width: 1200px; margin: 2rem auto; padding: 0 1.5rem; }
  h1 { color: var(--accent); margin-bottom: 1.5rem; font-size: 1.5rem; }
  h2 { color: var(--text); margin: 1.5rem 0 0.75rem; font-size: 1.1rem; }
  .cards { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 2rem; }
  .card { background: var(--surface); border: 1px solid var(--border);
          border-radius: 6px; padding: 1.25rem; min-width: 140px; flex: 1; }
  .card .num { font-size: 2rem; font-weight: 700; }
  .card .label { color: var(--muted); font-size: 0.85rem; margin-top: 0.25rem; }
  .ok { color: var(--ok); } .warn { color: var(--warn); } .crit { color: var(--crit); }
  .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
           font-size: 0.8rem; font-weight: 700; }
  .badge-ok { background: #27ae6033; color: var(--ok); }
  .badge-warn { background: #f39c1233; color: var(--warn); }
  .badge-crit { background: #e74c3c33; color: var(--crit); }
  table { width: 100%; border-collapse: collapse; margin-top: 0.5rem; }
  th, td { padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }
  th { color: var(--accent); font-weight: 600; font-size: 0.85rem; }
  tr:hover { background: #ffffff08; }
  .filters { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .filters select, .filters input { background: var(--surface); color: var(--text);
    border: 1px solid var(--border); border-radius: 4px; padding: 0.35rem 0.5rem;
    font-family: inherit; font-size: 0.85rem; }
  .filters button { background: var(--accent); color: var(--bg); border: none;
    border-radius: 4px; padding: 0.35rem 1rem; font-weight: 600; cursor: pointer; }
  .raw-output { background: #0a0a1a; border: 1px solid var(--border);
    border-radius: 4px; padding: 0.75rem; white-space: pre-wrap;
    font-size: 0.8rem; max-height: 300px; overflow-y: auto; margin-top: 0.5rem; display: none; }
  .raw-output.open { display: block; }
  .toggle-raw { color: var(--accent); cursor: pointer; font-size: 0.8rem; }
  /* chat styles */
  .chat-container { display: flex; flex-direction: column; height: calc(100vh - 180px);
    background: var(--surface); border: 1px solid var(--border); border-radius: 6px; }
  .chat-messages { flex: 1; overflow-y: auto; padding: 1rem; }
  .msg { margin-bottom: 0.75rem; padding: 0.5rem 0.75rem; border-radius: 4px; }
  .msg-user { background: #00d2ff11; border-left: 3px solid var(--accent); }
  .msg-agent { background: #ffffff05; border-left: 3px solid var(--muted); }
  .msg-tool { background: #f39c1211; border-left: 3px solid var(--warn);
    font-size: 0.8rem; color: var(--warn); }
  .msg-err { background: #e74c3c11; border-left: 3px solid var(--crit);
    color: var(--crit); }
  .chat-input { display: flex; padding: 0.75rem; border-top: 1px solid var(--border); }
  .chat-input input { flex: 1; background: var(--bg); color: var(--text);
    border: 1px solid var(--border); border-radius: 4px; padding: 0.5rem 0.75rem;
    font-family: inherit; font-size: 0.95rem; }
  .chat-input button { background: var(--accent); color: var(--bg); border: none;
    border-radius: 4px; padding: 0.5rem 1.25rem; margin-left: 0.5rem;
    font-weight: 600; cursor: pointer; }
  /* approval modal */
  .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: #000000aa; z-index: 100; justify-content: center; align-items: center; }
  .modal-overlay.open { display: flex; }
  .modal { background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 1.5rem; max-width: 600px; width: 90%; }
  .modal h2 { margin-top: 0; }
  .modal pre { background: #0a0a1a; padding: 0.75rem; border-radius: 4px;
    overflow-x: auto; font-size: 0.85rem; margin: 0.75rem 0; }
  .modal-actions { display: flex; gap: 0.75rem; justify-content: flex-end; }
  .btn-approve { background: var(--ok); color: #fff; border: none; border-radius: 4px;
    padding: 0.5rem 1.5rem; font-weight: 700; cursor: pointer; }
  .btn-deny { background: var(--crit); color: #fff; border: none; border-radius: 4px;
    padding: 0.5rem 1.5rem; font-weight: 700; cursor: pointer; }
  .btn-cancel { background: var(--muted); color: #fff; border: none; border-radius: 4px;
    padding: 0.5rem 1.5rem; cursor: pointer; }
  .spinner { display: inline-block; width: 0.85rem; height: 0.85rem;
    border: 2px solid var(--muted); border-top-color: var(--accent);
    border-radius: 50%; animation: spin 0.6s linear infinite; margin-right: 0.3rem; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .empty-state { color: var(--muted); text-align: center; padding: 3rem; }
  .timestamp { color: var(--muted); font-size: 0.75rem; }
  a { color: var(--accent); }
"""

NAV = """<nav>
  <a href="/">Dashboard</a>
  <a href="/hosts">Hosts</a>
  <a href="/inspections">Inspections</a>
  <a href="/audit">Audit</a>
  <a href="/config">Config</a>
  <a href="/chat">Chat</a>
</nav>"""


def base_page(content: str, extra_head: str = "", extra_scripts: str = "") -> str:
    # Use string concatenation to avoid f-string {{}} escaping issues
    # with JS code containing curly braces.
    tpl = "<!DOCTYPE html>\n<html lang=\"en\">\n<head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>ops-agent</title>\n<style>" + STYLE + "</style>" + extra_head + """
</head>
<body>
""" + NAV + """
<main>
""" + content + """
</main>
""" + extra_scripts + """
</body>
</html>"""
    return tpl


def dashboard_page(summary: dict, alerts: list[dict],
                   config: dict | None = None) -> str:
    checks_list = config.get("checks", []) if config else []
    checks_html = ""
    if checks_list:
        checks_html = '<div class="card" style="flex:2;min-width:300px">' \
                      '<div class="label" style="margin-bottom:0.5rem">Available Checks</div>' \
                      '<div style="display:flex;flex-wrap:wrap;gap:0.3rem">' \
                      + "".join('<span class="badge badge-ok">' + c + '</span>' for c in checks_list) \
                      + '</div></div>'
    content = '<h1>Dashboard</h1>\n<div class="cards">\n' \
              '<div class="card"><div class="num ok">' + str(summary.get('ok', 0)) + '</div><div class="label">OK</div></div>\n' \
              '<div class="card"><div class="num warn">' + str(summary.get('warn', 0)) + '</div><div class="label">WARN</div></div>\n' \
              '<div class="card"><div class="num crit">' + str(summary.get('crit', 0)) + '</div><div class="label">CRIT</div></div>\n' \
              '<div class="card"><div class="num" style="color:var(--accent)">' + str(summary.get('total', 0)) + '</div><div class="label">Total</div></div>\n' \
              + checks_html + '\n</div>\n' \
              '<h2>Recent Alerts</h2>\n' + alerts_table(alerts)
    extra_scripts = '<div id="health-status" class="timestamp" style="margin-top:1rem"></div>\n' \
                    '<script>\n' \
                    "fetch('/api/health').then(function(r){return r.json();}).then(function(d){\n" \
                    "  var el=document.getElementById('health-status');\n" \
                    "  if(el)el.textContent='Status: '+d.status+' ('+d.hosts+' hosts, '+d.checks+' checks)';\n" \
                    "}).catch(function(){});\n" \
                    "setInterval(function(){location.reload();}, 60000);\n" \
                    '</script>'
    return base_page(content, extra_scripts=extra_scripts)


def hosts_page(hosts_data: list[dict]) -> str:
    rows = "".join(
        '<tr class="host-row" data-alias="' + h["alias"] + '" data-address="' + h.get("address", "") + '" data-status="' + h.get("worst_status", "ok") + '" data-tags="' + ",".join(h.get("tags", [])) + '">' \
        '<td><a href="/hosts/' + h["alias"] + '">' + h["alias"] + '</a></td>' \
        '<td>' + h.get("address", "") + '</td>' \
        '<td><span class="badge badge-' + h.get("worst_status", "ok") + '">' + h.get("worst_status", "ok").upper() + '</span></td>' \
        '<td>' + ",".join(h.get("tags", [])) + '</td></tr>'
        for h in hosts_data
    ) or '<tr><td colspan="4" class="empty-state">No hosts found</td></tr>'
    content = '<h1>Hosts</h1>\n' \
              '<div class="filters">\n' \
              '<input type="text" id="host-search" placeholder="Search hosts...">\n' \
              '<select id="host-filter-status"><option value="">All Status</option><option value="ok">OK</option><option value="warn">WARN</option><option value="crit">CRIT</option></select>\n' \
              '<select id="host-filter-tag"><option value="">All Tags</option></select>\n' \
              '<button onclick="applyHostFilters()">Filter</button>\n' \
              '</div>\n' \
              '<table><thead><tr><th>Alias</th><th>Address</th><th>Status</th><th>Tags</th></tr></thead><tbody id="host-body">' + rows + '</tbody></table>'
    extra_scripts = '<script>\n' \
                    '// Populate tag filter\n' \
                    'var allTags=new Set();\n' \
                    "document.querySelectorAll('.host-row').forEach(function(r){r.dataset.tags.split(',').forEach(function(t){if(t)allTags.add(t);});});\n" \
                    'var tagSel=document.getElementById(\'host-filter-tag\');\n' \
                    'allTags.forEach(function(t){var o=document.createElement(\'option\');o.value=t;o.textContent=t;tagSel.appendChild(o);});\n' \
                    'function applyHostFilters(){\n' \
                    "  var q=document.getElementById('host-search').value.toLowerCase();\n" \
                    "  var st=document.getElementById('host-filter-status').value;\n" \
                    "  var tg=document.getElementById('host-filter-tag').value;\n" \
                    '  document.querySelectorAll(\'.host-row\').forEach(function(r){\n' \
                    '    var matchQ=!q||r.dataset.alias.toLowerCase().includes(q)||r.dataset.address.toLowerCase().includes(q);\n' \
                    '    var matchSt=!st||r.dataset.status===st;\n' \
                    '    var matchTg=!tg||r.dataset.tags.split(\',\').includes(tg);\n' \
                    "    r.style.display=(matchQ&&matchSt&&matchTg)?'':'none';\n" \
                    '  });\n' \
                    "}\n" \
                    "document.getElementById('host-search').addEventListener('input',applyHostFilters);\n" \
                    '</script>'
    return base_page(content, extra_scripts=extra_scripts)


def host_detail_page(alias: str, inspections: list[dict],
                    trend_html: str = "") -> str:
    rows = "".join(
        '<tr><td class="timestamp">' + i.get("ts", "")[:19] + '</td>' \
        '<td>' + i.get("check_name", "") + '</td>' \
        '<td><span class="badge badge-' + i.get("status", "ok") + '">' + i.get("status", "").upper() + '</span></td>' \
        '<td>' + _format_value(i.get("value", {})) + '</td>' \
        '<td><span class="toggle-raw" onclick="this.nextElementSibling.classList.toggle(\'open\')">show</span>' \
        '<div class="raw-output">' + _escape(i.get("raw_stdout", "")) + '</div></td></tr>'
        for i in inspections
    ) or '<tr><td colspan="5" class="empty-state">No inspection history</td></tr>'
    content = '<h1>' + alias + '</h1>\n' \
              '<div id="host-trend-chart" style="margin:1rem 0"></div>\n' \
              + trend_html + '\n' \
              '<h2>Recent Inspections</h2>\n' \
              '<table><thead><tr><th>Time</th><th>Check</th><th>Status</th><th>Value</th><th>Raw</th></tr></thead>\n' \
              '<tbody>' + rows + '</tbody></table>'
    extra_scripts = '<script>\n' \
                    "fetch('/api/hosts/'+window.location.pathname.split('/').pop()+'/trends?days=7').then(function(r){return r.json();}).then(function(data){\n" \
                    "  var chart=document.getElementById('host-trend-chart');\n" \
                    '  if(!Object.keys(data).length)return;\n' \
                    "  var html='<h2>Trends (7d)</h2><div style=\"display:flex;flex-wrap:wrap;gap:1rem\">';\n" \
                    '  for(var key in data){\n' \
                    '    var d=data[key];\n' \
                    '    if(d.points.length<2)continue;\n' \
                    '    var vals=d.points.map(function(p){return p.value;});\n' \
                    '    var first=vals[0],last=vals[vals.length-1];\n' \
                    '    var delta=last-first;\n' \
                    "    var cls=delta>0?'crit':'ok';\n" \
                    "    html+='<div style=\"background:var(--surface);padding:0.75rem;border-radius:4px;min-width:180px\">';\n" \
                    "    html+='<strong>'+key+'</strong><br>';\n" \
                    "    html+='<span class='+cls+'>'+first+' -> '+last+' ('+(delta>0?'+':'')+delta.toFixed(1)+')</span>';\n" \
                    "    html+='</div>';\n" \
                    '  }\n' \
                    "  html+='</div>';\n" \
                    '  chart.innerHTML=html;\n' \
                    "}).catch(function(){});\n" \
                    '</script>'
    return base_page(content, extra_scripts=extra_scripts)


def inspections_page(hosts: list, checks: list, inspections: list[dict]) -> str:
    host_opts = "".join('<option value="' + h + '">' + h + '</option>' for h in hosts)
    check_opts = "".join('<option value="' + c + '">' + c + '</option>' for c in checks)
    rows = "".join(
        '<tr><td class="timestamp">' + i.get("ts", "")[:19] + '</td>' \
        '<td>' + i.get("host", "") + '</td>' \
        '<td>' + i.get("check_name", "") + '</td>' \
        '<td><span class="badge badge-' + i.get("status", "ok") + '">' + i.get("status", "").upper() + '</span></td>' \
        '<td>' + _format_value(i.get("value", {})) + '</td></tr>'
        for i in inspections
    ) or '<tr><td colspan="5" class="empty-state">No inspections found</td></tr>'
    content = '<h1>Inspections</h1>\n' \
              '<div class="filters">\n' \
              '<select id="fhost"><option value="">All Hosts</option>' + host_opts + '</select>\n' \
              '<select id="fcheck"><option value="">All Checks</option>' + check_opts + '</select>\n' \
              '<select id="fstatus"><option value="">All Status</option><option value="ok">OK</option><option value="warn">WARN</option><option value="crit">CRIT</option></select>\n' \
              '<button onclick="applyFilters()">Filter</button>\n' \
              '</div>\n' \
              '<table><thead><tr><th>Time</th><th>Host</th><th>Check</th><th>Status</th><th>Value</th></tr></thead>\n' \
              '<tbody id="insp-body">' + rows + '</tbody></table>'
    extra_scripts = '<script>\n' \
                    'function applyFilters(){\n' \
                    '  var p=new URLSearchParams();\n' \
                    "  var h=document.getElementById('fhost').value; if(h)p.set('host',h);\n" \
                    "  var c=document.getElementById('fcheck').value; if(c)p.set('check',c);\n" \
                    "  var s=document.getElementById('fstatus').value; if(s)p.set('status',s);\n" \
                    "  p.set('limit','200');\n" \
                    "  fetch('/api/inspections?'+p).then(function(r){return r.json();}).then(function(data){\n" \
                    "    var tb=document.getElementById('insp-body');\n" \
                    "    tb.innerHTML=data.length?data.map(function(i){return '<tr><td class=\"timestamp\">'+(i.ts||'').slice(0,19)+'</td><td>'+i.host+'</td><td>'+i.check_name+'</td><td><span class=\"badge badge-'+i.status+'\">'+i.status.toUpperCase()+'</span></td><td>'+JSON.stringify(i.value)+'</td></tr>';}).join(''):'<tr><td colspan=\"5\" class=\"empty-state\">No inspections found</td></tr>';\n" \
                    '  });\n' \
                    "}\n" \
                    '</script>'
    return base_page(content, extra_scripts=extra_scripts)


def chat_page() -> str:
    extra_head = ""
    extra_scripts = '<div class="modal-overlay" id="approval-modal">\n' \
                    '<div class="modal"><h2>Approval Required</h2>\n' \
                    '<pre id="approval-command"></pre>\n' \
                    '<div class="modal-actions">\n' \
                    '<button class="btn-approve" onclick="resolveApproval(true)">Approve</button>\n' \
                    '<button class="btn-deny" onclick="resolveApproval(false)">Deny</button>\n' \
                    '</div></div></div>\n' \
                    '<script>\n' \
                    'var sessionId=null, pendingApproval=null;\n' \
                    "var msgs=document.getElementById('msgs');\n" \
                    "function addMsg(cls,html){var d=document.createElement('div');d.className='msg msg-'+cls;d.innerHTML=html;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;}\n" \
                    "function sendMsg(){\n" \
                    "  var inp=document.getElementById('chat-input');\n" \
                    "  var text=inp.value.trim(); if(!text)return;\n" \
                    "  addMsg('user',text); inp.value='';\n" \
                    "  var body={message:text};\n" \
                    '  if(sessionId)body.session_id=sessionId;\n' \
                    "  var es=new EventSource('/api/chat?'+new URLSearchParams(body));\n" \
                    "  es.addEventListener('text',function(e){addMsg('agent',e.data);});\n" \
                    "  es.addEventListener('tool_use',function(e){addMsg('tool','<span class=\"spinner\"></span>Running: '+e.data);});\n" \
                    "  es.addEventListener('tool_result',function(e){addMsg('tool','Done: '+e.data);});\n" \
                    "  es.addEventListener('approval_required',function(e){\n" \
                    "    document.getElementById('approval-command').textContent=e.data;\n" \
                    "    document.getElementById('approval-modal').classList.add('open');\n" \
                    "    pendingApproval=new Promise(function(resolve){window._approve=resolve;});\n" \
                    "  });\n" \
                    "  es.addEventListener('session',function(e){sessionId=e.data;});\n" \
                    "  es.addEventListener('done',function(e){es.close();});\n" \
                    "  es.addEventListener('error',function(e){addMsg('err','Connection error');es.close();});\n" \
                    "}\n" \
                    "function resolveApproval(approved){\n" \
                    "  document.getElementById('approval-modal').classList.remove('open');\n" \
                    "  if(window._approve){window._approve(approved);window._approve=null;}\n" \
                    "  if(sessionId) fetch('/api/chat/'+sessionId+'/approve',{method:'POST',\n" \
                    "    headers:{'Content-Type':'application/json'},body:JSON.stringify({approved:approved})});\n" \
                    "}\n" \
                    "document.getElementById('chat-input').addEventListener('keydown',function(e){if(e.key==='Enter')sendMsg();});\n" \
                    '</script>'
    content = '<h1>Chat</h1>\n' \
              '<div class="chat-container">\n' \
              '<div class="chat-messages" id="msgs"></div>\n' \
              '<div class="chat-input">\n' \
              '<input id="chat-input" placeholder="Ask about your fleet..." autofocus>\n' \
              '<button onclick="sendMsg()">Send</button>\n' \
              '</div>\n' \
              '</div>'
    return base_page(content, extra_head, extra_scripts)


def alerts_table(alerts: list[dict]) -> str:
    if not alerts:
        return '<p class="empty-state">No recent alerts</p>'
    rows = "".join(
        '<tr><td class="timestamp">' + a.get("ts", "")[:19] + '</td>' \
        '<td>' + a.get("host", "") + '</td><td>' + a.get("check_name", "") + '</td>' \
        '<td><span class="badge badge-' + a.get("status", "ok") + '">' + a.get("status", "").upper() + '</span></td>' \
        '<td>' + _format_value(a.get("value", {})) + '</td></tr>'
        for a in alerts
    )
    return '<table><thead><tr><th>Time</th><th>Host</th><th>Check</th><th>Status</th><th>Value</th></tr></thead><tbody>' + rows + '</tbody></table>'


def _format_value(value: dict) -> str:
    if not value:
        return "-"
    parts = [k + "=" + str(v) for k, v in value.items()]
    return ", ".join(parts[:3])  # limit to 3 pairs


def _escape(text: str) -> str:
    """Escape text for safe HTML embedding."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("'", "&#x27;")
            .replace('"', "&quot;"))


def config_page(info: dict) -> str:
    checks_html = "".join(
        '<span class="badge badge-ok">' + c + '</span>' for c in info.get("checks", [])
    )
    content = '<h1>Configuration</h1>\n' \
              '<div class="cards">\n' \
              '<div class="card"><div class="num" style="color:var(--accent)">' + str(info.get("version", "?")) + '</div><div class="label">Version</div></div>\n' \
              '<div class="card"><div class="num">' + str(info.get("hosts", 0)) + '</div><div class="label">Managed Hosts</div></div>\n' \
              '<div class="card" style="flex:2;min-width:300px"><div class="label" style="margin-bottom:0.5rem">Built-in Checks</div><div style="display:flex;flex-wrap:wrap;gap:0.3rem">' + checks_html + '</div></div>\n' \
              '</div>'
    return base_page(content)


def audit_page(rows: list[dict]) -> str:
    if not rows:
        content = '<h1>Audit Log</h1><p class="empty-state">No audit records found</p>'
    else:
        table_rows = "".join(
            '<tr><td class="timestamp">' + r.get("ts", "")[:19] + '</td>' \
            '<td>' + r.get("host", "") + '</td>' \
            '<td>' + _escape(r.get("command", "")) + '</td>' \
            '<td>' + str(r.get("rc", "")) + '</td>' \
            '<td>' + r.get("verdict", "") + '</td>' \
            '<td>' + r.get("initiated_by", "") + '</td>' \
            '<td>' + r.get("approved_by", "") + '</td></tr>'
            for r in rows
        )
        content = '<h1>Audit Log</h1>\n' \
                  '<div class="filters">\n' \
                  '<select id="audit-filter-verdict"><option value="">All Verdicts</option><option value="auto_allow">Auto Allow</option><option value="require_approval">Require Approval</option><option value="deny">Deny</option></select>\n' \
                  '<button onclick="applyAuditFilters()">Filter</button>\n' \
                  '</div>\n' \
                  '<table><thead><tr><th>Time</th><th>Host</th><th>Command</th><th>RC</th><th>Verdict</th><th>By</th><th>Approved By</th></tr></thead>\n' \
                  '<tbody id="audit-body">' + table_rows + '</tbody></table>'
    extra_scripts = '<script>\n' \
                    'function applyAuditFilters(){\n' \
                    "  var v=document.getElementById('audit-filter-verdict').value;\n" \
                    "  document.querySelectorAll('#audit-body tr').forEach(function(r){\n" \
                    "    if(!v)r.style.display='';\n" \
                    "    else r.style.display=r.cells[4].textContent.toLowerCase().replace(' ','_')===v||r.cells[4].textContent===v?'':'none';\n" \
                    "  });\n" \
                    "}\n" \
                    '</script>'
    return base_page(content, extra_scripts=extra_scripts)
