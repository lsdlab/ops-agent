"""Embedded HTML templates for the web console.

Uses Python str.format() — no Jinja2 dependency needed for five pages.
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
  <a href="/chat">Chat</a>
</nav>"""


def base_page(content: str, extra_head: str = "", extra_scripts: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ops-agent</title>
<style>{STYLE}</style>{extra_head}
</head>
<body>
{NAV}
<main>
{content}
</main>
{extra_scripts}
</body>
</html>"""


def dashboard_page(summary: dict, alerts: list[dict]) -> str:
    content = f"""<h1>Dashboard</h1>
<div class="cards">
  <div class="card"><div class="num ok">{summary['ok']}</div><div class="label">OK</div></div>
  <div class="card"><div class="num warn">{summary['warn']}</div><div class="label">WARN</div></div>
  <div class="card"><div class="num crit">{summary['crit']}</div><div class="label">CRIT</div></div>
  <div class="card"><div class="num" style="color:var(--accent)">{summary['total']}</div><div class="label">Total</div></div>
</div>
<h2>Recent Alerts</h2>
{alerts_table(alerts)}
<script>setInterval(()=>location.reload(), 60000)</script>"""
    return base_page(content)


def hosts_page(hosts_data: list[dict]) -> str:
    rows = "".join(
        f'<tr><td><a href="/hosts/{h["alias"]}">{h["alias"]}</a></td>'
        f'<td>{h.get("address","")}</td>'
        f'<td><span class="badge badge-{h.get("worst_status","ok")}">{h.get("worst_status","ok").upper()}</span></td></tr>'
        for h in hosts_data
    ) or '<tr><td colspan="3" class="empty-state">No hosts found</td></tr>'
    content = f"""<h1>Hosts</h1>
<table><thead><tr><th>Alias</th><th>Address</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>"""
    return base_page(content)


def host_detail_page(alias: str, inspections: list[dict],
                    trend_html: str = "") -> str:
    rows = "".join(
        f'<tr><td class="timestamp">{i.get("ts","")[:19]}</td>'
        f'<td>{i.get("check_name","")}</td>'
        f'<td><span class="badge badge-{i.get("status","ok")}">{i.get("status","").upper()}</span></td>'
        f'<td>{_format_value(i.get("value",{}))}</td>'
        f'<td><span class="toggle-raw" onclick="this.nextElementSibling.classList.toggle(\'open\')">show</span>'
        f'<div class="raw-output">{_escape(i.get("raw_stdout",""))}</div></td></tr>'
        for i in inspections
    ) or '<tr><td colspan="5" class="empty-state">No inspection history</td></tr>'
    content = f"""<h1>{alias}</h1>
{trend_html}
<h2>Recent Inspections</h2>
<table><thead><tr><th>Time</th><th>Check</th><th>Status</th><th>Value</th><th>Raw</th></tr></thead>
<tbody>{rows}</tbody></table>"""
    return base_page(content)


def inspections_page(hosts: list, checks: list, inspections: list[dict]) -> str:
    host_opts = "".join(f'<option value="{h}">{h}</option>' for h in hosts)
    check_opts = "".join(f'<option value="{c}">{c}</option>' for c in checks)
    rows = "".join(
        f'<tr><td class="timestamp">{i.get("ts","")[:19]}</td>'
        f'<td>{i.get("host","")}</td>'
        f'<td>{i.get("check_name","")}</td>'
        f'<td><span class="badge badge-{i.get("status","ok")}">{i.get("status","").upper()}</span></td>'
        f'<td>{_format_value(i.get("value",{}))}</td></tr>'
        for i in inspections
    ) or '<tr><td colspan="5" class="empty-state">No inspections found</td></tr>'
    content = f"""<h1>Inspections</h1>
<div class="filters">
  <select id="fhost"><option value="">All Hosts</option>{host_opts}</select>
  <select id="fcheck"><option value="">All Checks</option>{check_opts}</select>
  <select id="fstatus"><option value="">All Status</option><option value="ok">OK</option><option value="warn">WARN</option><option value="crit">CRIT</option></select>
  <button onclick="applyFilters()">Filter</button>
</div>
<table><thead><tr><th>Time</th><th>Host</th><th>Check</th><th>Status</th><th>Value</th></tr></thead>
<tbody id="insp-body">{rows}</tbody></table>
<script>
function applyFilters(){{
  const p=new URLSearchParams();
  const h=document.getElementById('fhost').value; if(h)p.set('host',h);
  const c=document.getElementById('fcheck').value; if(c)p.set('check',c);
  const s=document.getElementById('fstatus').value; if(s)p.set('status',s);
  p.set('limit','200');
  fetch('/api/inspections?'+p).then(r=>r.json()).then(data=>{{
    const tb=document.getElementById('insp-body');
    tb.innerHTML=data.length?data.map(i=>`<tr><td class="timestamp">${{(i.ts||'').slice(0,19)}}</td><td>${{i.host}}</td><td>${{i.check_name}}</td><td><span class="badge badge-${{i.status}}">${{i.status.toUpperCase()}}</span></td><td>${{JSON.stringify(i.value)}}</td></tr>`).join(''):'<tr><td colspan="5" class="empty-state">No inspections found</td></tr>';
  }});
}}
</script>"""
    return base_page(content)


def chat_page() -> str:
    extra_head = ""
    extra_scripts = f"""<div class="modal-overlay" id="approval-modal">
<div class="modal"><h2>Approval Required</h2>
<pre id="approval-command"></pre>
<div class="modal-actions">
  <button class="btn-approve" onclick="resolveApproval(true)">Approve</button>
  <button class="btn-deny" onclick="resolveApproval(false)">Deny</button>
</div></div></div>
<script>
let sessionId=null, pendingApproval=null;
const msgs=document.getElementById('msgs');
function addMsg(cls,html){{const d=document.createElement('div');d.className='msg msg-'+cls;d.innerHTML=html;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;}}
function sendMsg(){{
  const inp=document.getElementById('chat-input');
  const text=inp.value.trim(); if(!text)return;
  addMsg('user',text); inp.value='';
  const body={{message:text}};
  if(sessionId)body.session_id=sessionId;
  const es=new EventSource('/api/chat?'+new URLSearchParams(body));
  es.addEventListener('text',e=>addMsg('agent',e.data));
  es.addEventListener('tool_use',e=>addMsg('tool','<span class="spinner"></span>Running: '+e.data));
  es.addEventListener('tool_result',e=>addMsg('tool','Done: '+e.data));
  es.addEventListener('approval_required',e=>{{
    document.getElementById('approval-command').textContent=e.data;
    document.getElementById('approval-modal').classList.add('open');
    pendingApproval=new Promise((resolve)=>{{window._approve=resolve;}});
  }});
  es.addEventListener('session',e=>sessionId=e.data);
  es.addEventListener('done',e=>es.close());
  es.addEventListener('error',e=>{{addMsg('err','Connection error');es.close();}});
}}
function resolveApproval(approved){{
  document.getElementById('approval-modal').classList.remove('open');
  if(window._approve){{window._approve(approved);window._approve=null;}}
  if(sessionId) fetch('/api/chat/'+sessionId+'/approve',{{method:'POST',
    headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{approved}})}});
}}
document.getElementById('chat-input').addEventListener('keydown',e=>{{if(e.key==='Enter')sendMsg();}});
</script>"""
    content = """<h1>Chat</h1>
<div class="chat-container">
  <div class="chat-messages" id="msgs"></div>
  <div class="chat-input">
    <input id="chat-input" placeholder="Ask about your fleet..." autofocus>
    <button onclick="sendMsg()">Send</button>
  </div>
</div>"""
    return base_page(content, extra_head, extra_scripts)


def alerts_table(alerts: list[dict]) -> str:
    if not alerts:
        return '<p class="empty-state">No recent alerts</p>'
    rows = "".join(
        f'<tr><td class="timestamp">{a.get("ts","")[:19]}</td>'
        f'<td>{a.get("host","")}</td><td>{a.get("check_name","")}</td>'
        f'<td><span class="badge badge-{a.get("status","ok")}">{a.get("status","").upper()}</span></td>'
        f'<td>{_format_value(a.get("value",{}))}</td></tr>'
        for a in alerts
    )
    return f"<table><thead><tr><th>Time</th><th>Host</th><th>Check</th><th>Status</th><th>Value</th></tr></thead><tbody>{rows}</tbody></table>"


def _format_value(value: dict) -> str:
    if not value:
        return "-"
    parts = [f"{k}={v}" for k, v in value.items()]
    return ", ".join(parts[:3])  # limit to 3 pairs


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
