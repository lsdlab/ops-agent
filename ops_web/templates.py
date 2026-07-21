"""Embedded HTML templates for the ops-agent web console (Tailwind redesign).

Server-rendered string templates + Tailwind (Play CDN) — no build step, no
Node. JS is kept in plain concatenated strings (no f-strings) to avoid {{}}
escaping issues.

Design language: a dark, layered "fleet pulse" console — deep blue-slate base,
semantic status colors (emerald/amber/red), sky for interactive, Space Grotesk
display + IBM Plex Sans body + JetBrains Mono data.
"""

# ---------------------------------------------------------------------------
# Head: Tailwind CDN + design tokens + fonts + ambient background styles
# ---------------------------------------------------------------------------

HEAD = """
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: {
      colors: {
        ink: {950:'#080d18',900:'#0d1526',850:'#101a2e',800:'#14203a',700:'#1d2c4d',600:'#2a3d66',500:'#3b5185'},
        ok:   {DEFAULT:'#34d399', soft:'rgba(52,211,153,.12)', ring:'rgba(52,211,153,.35)'},
        warn: {DEFAULT:'#fbbf24', soft:'rgba(251,191,36,.12)', ring:'rgba(251,191,36,.35)'},
        crit: {DEFAULT:'#f87171', soft:'rgba(248,113,113,.13)', ring:'rgba(248,113,113,.38)'},
        acc:  {DEFAULT:'#38bdf8', soft:'rgba(56,189,248,.12)', dim:'#7dd3fc'},
      },
      fontFamily: {
        disp: ['"Space Grotesk"','system-ui','sans-serif'],
        body: ['"IBM Plex Sans"','system-ui','sans-serif'],
        mono: ['"JetBrains Mono"','ui-monospace','SFMono-Regular','monospace'],
      },
      boxShadow: {
        tile: '0 1px 0 0 rgba(255,255,255,.04) inset, 0 8px 24px -12px rgba(0,0,0,.6)',
      },
    }
  }
}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  /* ambient layered background: faint grid + two soft glows */
  .bg-ambient{
    background:
      radial-gradient(900px 500px at 12% -10%, rgba(56,189,248,.07), transparent 60%),
      radial-gradient(800px 520px at 100% 110%, rgba(167,139,250,.055), transparent 60%),
      linear-gradient(rgba(148,163,184,.045) 1px, transparent 1px),
      linear-gradient(90deg, rgba(148,163,184,.045) 1px, transparent 1px);
    background-size:auto,auto,34px 34px,34px 34px;
  }
  .scroll-slim::-webkit-scrollbar{width:8px;height:8px}
  .scroll-slim::-webkit-scrollbar-thumb{background:#1d2c4d;border-radius:8px}
  .scroll-slim::-webkit-scrollbar-track{background:transparent}
  @keyframes pulse-dot{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.45;transform:scale(.8)}}
  .pulse-dot{animation:pulse-dot 1.8s ease-in-out infinite}
  @keyframes ping-ring{0%{transform:scale(.6);opacity:.7}80%,100%{transform:scale(2.2);opacity:0}}
  .ping-ring{animation:ping-ring 1.8s cubic-bezier(0,0,.2,1) infinite}
  @keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
  .rise{animation:rise .35s ease both}
  @keyframes blink{0%,100%{opacity:.15}50%{opacity:1}}
  .typing i{display:inline-block;width:5px;height:5px;border-radius:99px;background:#7dd3fc;margin-right:4px;animation:blink 1.2s infinite}
  .typing i:nth-child(2){animation-delay:.15s}.typing i:nth-child(3){animation-delay:.3s}
</style>
"""

# ---------------------------------------------------------------------------
# Shared bits: nav, helpers
# ---------------------------------------------------------------------------

def _icon(name):
    icons = {
        "dash":  '<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z"/>',
        "hosts": '<path stroke-linecap="round" stroke-linejoin="round" d="M21.75 17.25v-.228a4.5 4.5 0 00-.12-1.03l-2.268-9.64a3.375 3.375 0 00-3.285-2.602H7.923a3.375 3.375 0 00-3.285 2.602l-2.268 9.64a4.5 4.5 0 00-.12 1.03v.228m19.5 0a3 3 0 01-3 3H5.25a3 3 0 01-3-3m19.5 0a3 3 0 00-3-3H5.25a3 3 0 00-3 3m16.5 0h.008v.008h-.008v-.008zm-3 0h.008v.008h-.008v-.008z"/>',
        "insp":  '<path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z"/>',
        "audit": '<path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z"/>',
        "chat":  '<path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"/>',
        "conf":  '<path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.28z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>',
    }
    return ('<svg class="w-[18px] h-[18px] shrink-0" fill="none" viewBox="0 0 24 24" stroke-width="1.6" stroke="currentColor">'
            + icons.get(name, "") + "</svg>")


_NAV = [
    ("/", "Dashboard", "dash"),
    ("/hosts", "Hosts", "hosts"),
    ("/inspections", "Inspections", "insp"),
    ("/audit", "Audit", "audit"),
    ("/chat", "Chat", "chat"),
    ("/config", "Config", "conf"),
]


def _nav_html(active: str) -> str:
    items = ""
    for href, label, icon in _NAV:
        is_active = (href == active)
        cls = ("flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150 group "
               + ("bg-acc-soft text-acc shadow-tile" if is_active
                  else "text-slate-400 hover:text-slate-100 hover:bg-ink-800/70"))
        items += ('<a href="' + href + '" class="' + cls + '">'
                  + '<span class="' + ("text-acc" if is_active else "text-slate-500 group-hover:text-slate-300") + '">'
                  + _icon(icon) + "</span>" + label + "</a>")
    return items


def base_page(content: str, title: str = "ops-agent", active: str = "/",
              extra_head: str = "", extra_scripts: str = "") -> str:
    nav = _nav_html(active)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>" + title + " · ops-agent</title>" + HEAD + extra_head + "</head>\n"
        "<body class=\"bg-ink-950 text-slate-300 font-body antialiased\">\n"
        "<div class=\"fixed inset-0 bg-ambient pointer-events-none\"></div>\n"
        "<div class=\"relative flex h-screen overflow-hidden\">\n"
        # ---- sidebar ----
        "  <aside class=\"w-52 shrink-0 flex flex-col border-r border-ink-700/50 bg-ink-900/70 backdrop-blur-sm\">\n"
        "    <div class=\"px-4 h-14 flex items-center gap-2.5 border-b border-ink-700/50\">\n"
        "      <span class=\"w-7 h-7 rounded-md bg-gradient-to-br from-acc to-sky-600 flex items-center justify-center font-disp font-bold text-ink-950 text-sm shadow-lg shadow-acc/20\">&gt;_</span>\n"
        "      <span class=\"font-disp font-semibold text-slate-100 tracking-tight\">ops-agent</span>\n"
        "    </div>\n"
        "    <nav class=\"flex-1 px-2.5 py-4 space-y-1 scroll-slim overflow-y-auto\">" + nav + "</nav>\n"
        "    <div class=\"px-4 py-3 border-t border-ink-700/50 flex items-center gap-2 text-[11px] text-slate-500\">\n"
        "      <span id=\"sb-status\" class=\"w-1.5 h-1.5 rounded-full bg-slate-600\"></span>\n"
        "      <span id=\"sb-status-text\">connecting…</span>\n"
        "    </div>\n"
        "  </aside>\n"
        # ---- main column ----
        "  <div class=\"flex-1 flex flex-col min-w-0\">\n"
        "    <header class=\"h-14 shrink-0 flex items-center justify-between px-6 border-b border-ink-700/50 bg-ink-900/40 backdrop-blur-sm\">\n"
        "      <div class=\"flex items-center gap-2\" id=\"fleet-pulse\">\n"
        "        <span class=\"text-[11px] uppercase tracking-wider text-slate-500 mr-1\">fleet</span>\n"
        "      </div>\n"
        "      <div class=\"text-[11px] font-mono text-slate-500\" id=\"clock\"></div>\n"
        "    </header>\n"
        "    <main class=\"flex-1 overflow-y-auto scroll-slim\">\n"
        "      <div class=\"max-w-6xl mx-auto px-6 py-6\">" + content + "</div>\n"
        "    </main>\n"
        "  </div>\n"
        "</div>\n"
        "<script>\n" + _SHELL_JS + "</script>\n"
        + extra_scripts + "\n</body>\n</html>"
    )


# Shell JS: topbar fleet pulse, clock, sidebar status. Plain string (no f-string).
_SHELL_JS = """
(function(){
  function tick(){
    var c=document.getElementById('clock');
    if(c){var d=new Date();c.textContent=d.toISOString().slice(11,19)+' UTC';}
  }
  tick(); setInterval(tick,1000);
  function pulse(){
    fetch('/api/dashboard').then(function(r){return r.json();}).then(function(d){
      var s=d.summary||{};
      var fp=document.getElementById('fleet-pulse'); if(!fp)return;
      var dot=function(color,n,label){return '<span class=\"flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-ink-800/80 border border-ink-700/60\">'+
        '<span class=\"w-1.5 h-1.5 rounded-full pulse-dot\" style=\"background:'+color+'\"></span>'+
        '<span class=\"font-mono text-xs\" style=\"color:'+color+'\">'+n+'</span>'+
        '<span class=\"text-[10px] uppercase tracking-wide text-slate-500\">'+label+'</span></span>';};
      fp.innerHTML='<span class=\"text-[11px] uppercase tracking-wider text-slate-500 mr-1\">fleet</span>'
        + dot('#34d399', s.ok||0, 'ok') + dot('#fbbf24', s.warn||0, 'warn') + dot('#f87171', s.crit||0, 'crit');
      var sb=document.getElementById('sb-status'), sbt=document.getElementById('sb-status-text');
      if(sb){sb.className='w-1.5 h-1.5 rounded-full bg-ok pulse-dot'; sbt.textContent='daemon · live';}
    }).catch(function(){
      var sb=document.getElementById('sb-status-text'); if(sb)sb.textContent='offline';
    });
  }
  pulse(); setInterval(pulse, 20000);
})();
"""

# ---------------------------------------------------------------------------
# Small shared renderers
# ---------------------------------------------------------------------------

_STATUS_COLOR = {"ok": "#34d399", "warn": "#fbbf24", "crit": "#f87171"}


def badge(status: str) -> str:
    st = (status or "ok").lower()
    color = _STATUS_COLOR.get(st, "#94a3b8")
    return ('<span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-mono font-medium border" '
            'style="color:' + color + ';background:' + color + '14;border-color:' + color + '33">'
            '<span class="w-1.5 h-1.5 rounded-full" style="background:' + color + '"></span>'
            + st.upper() + "</span>")


def status_dot(status: str, pulse: bool = True) -> str:
    color = _STATUS_COLOR.get((status or "ok").lower(), "#94a3b8")
    ring = ('<span class="absolute inline-flex w-full h-full rounded-full ping-ring" style="background:' + color + '40"></span>'
            if pulse and status in ("warn", "crit") else "")
    return ('<span class="relative flex w-2.5 h-2.5">' + ring
            + '<span class="relative inline-flex w-2.5 h-2.5 rounded-full" style="background:' + color + '"></span></span>')


def _tag_chip(tag: str) -> str:
    return ('<span class="px-1.5 py-0.5 rounded text-[10px] font-mono bg-ink-800 border border-ink-700/70 text-slate-400">'
            + tag + "</span>")


def _section_title(text: str, sub: str = "") -> str:
    return ('<div class="flex items-baseline gap-3 mb-4"><h2 class="font-disp text-lg font-semibold text-slate-100 tracking-tight">'
            + text + "</h2>"
            + ('<span class="text-xs text-slate-500">' + sub + "</span>" if sub else "")
            + "</div>")


def _table(headers: list, body_rows: str) -> str:
    th = "".join('<th class="px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-slate-500">' + h + "</th>"
                 for h in headers)
    return ('<div class="rounded-xl border border-ink-700/60 bg-ink-900/60 shadow-tile overflow-hidden">'
            '<table class="w-full text-[13px]"><thead class="border-b border-ink-700/60 bg-ink-850/60"><tr>' + th + "</tr></thead>"
            '<tbody class="divide-y divide-ink-800/70">' + body_rows + "</tbody></table></div>")


def _empty(msg: str, colspan: int) -> str:
    return ('<tr><td colspan="' + str(colspan) + '" class="px-3 py-12 text-center text-sm text-slate-500">'
            '<div class="text-2xl mb-2 opacity-40">⌀</div>' + msg + "</td></tr>")


def _escape(text: str) -> str:
    return (str(text)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("'", "&#x27;").replace('"', "&quot;"))


def _format_value(value) -> str:
    if not value:
        return "–"
    if isinstance(value, dict):
        parts = [str(k) + "=" + str(v) for k, v in value.items()]
        return ", ".join(parts[:3])
    return str(value)


# ---------------------------------------------------------------------------
# Dashboard — "fleet pulse"
# ---------------------------------------------------------------------------

def dashboard_page(summary: dict, alerts: list, hosts_data: list,
                   config: dict | None = None) -> str:
    checks = (config or {}).get("checks", [])
    ok = summary.get("ok", 0); warn = summary.get("warn", 0)
    crit = summary.get("crit", 0); total = summary.get("total", 0)

    def stat(n, color, label):
        return ('<div class="flex flex-col"><span class="font-disp text-[32px] leading-none font-bold tabular-nums" style="color:'
                + color + '">' + str(n) + '</span>'
                '<span class="mt-1.5 text-[10px] uppercase tracking-[0.14em] text-slate-500">' + label + "</span></div>")

    checks_html = ""
    if checks:
        checks_html = ('<div class="ml-auto lg:text-right"><div class="text-[10px] uppercase tracking-[0.14em] text-slate-500 mb-2">'
                       + str(len(checks)) + ' checks armed</div><div class="flex flex-wrap gap-1.5 lg:justify-end max-w-md">'
                       + "".join('<span class="px-2 py-0.5 rounded-md text-[11px] font-mono text-acc bg-acc-soft border border-acc/20">'
                                 + c + "</span>" for c in checks) + "</div></div>")

    band = ('<section class="rounded-xl border border-ink-700/60 bg-ink-900/60 shadow-tile px-6 py-5 mb-6 rise">'
            '<div class="flex flex-wrap items-center gap-x-12 gap-y-4">'
            + stat(ok, "#34d399", "ok") + stat(warn, "#fbbf24", "warn")
            + stat(crit, "#f87171", "crit")
            + '<div class="w-px self-stretch bg-ink-700/60 hidden sm:block"></div>'
            + stat(total, "#38bdf8", "total runs")
            + checks_html + "</div></section>")

    # host matrix
    tiles = ""
    for h in hosts_data:
        st = h.get("worst_status", "ok")
        tags = "".join(_tag_chip(t) for t in h.get("tags", [])) or '<span class="text-[11px] text-slate-600">—</span>'
        tiles += ('<a href="/hosts/' + str(h["alias"]) + '" '
                  'class="group block rounded-xl border border-ink-700/60 bg-ink-900/60 shadow-tile p-4 '
                  'hover:border-acc/40 hover:bg-ink-850/70 hover:-translate-y-0.5 transition-all duration-150 rise">'
                  '<div class="flex items-center justify-between mb-3">'
                  '<div class="flex items-center gap-2.5">' + status_dot(st)
                  + '<span class="font-disp font-semibold text-slate-100 tracking-tight group-hover:text-acc transition-colors">'
                  + _escape(str(h["alias"])) + "</span></div>" + badge(st) + "</div>"
                  '<div class="font-mono text-xs text-slate-500 mb-3">' + _escape(str(h.get("address", ""))) + "</div>"
                  '<div class="flex flex-wrap gap-1.5">' + tags + "</div></a>")
    host_grid = ('<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">' + tiles + "</div>"
                 if tiles else '<div class="text-sm text-slate-500 py-8 text-center">No hosts in inventory</div>')

    # alerts timeline
    items = ""
    for a in alerts[:30]:
        color = _STATUS_COLOR.get(a.get("status", ""), "#94a3b8")
        items += ('<div class="relative pl-5 pb-4 border-l border-ink-700/60 last:border-l-0">'
                  '<span class="absolute -left-[5px] top-1 w-2.5 h-2.5 rounded-full" style="background:' + color + '"></span>'
                  '<div class="font-mono text-[11px] text-slate-500">' + _escape(str(a.get("ts", ""))[:19]) + "</div>"
                  '<div class="text-[13px] mt-0.5"><span class="font-medium text-slate-200">' + _escape(str(a.get("host", "")))
                  + '</span> <span class="text-slate-600">·</span> <span class="text-slate-400">' + _escape(str(a.get("check_name", "")))
                  + '</span></div><div class="text-xs text-slate-500 font-mono mt-0.5">' + _escape(_format_value(a.get("value")))
                  + "</div></div>")
    alerts_html = (items if items
                   else '<div class="text-sm text-slate-500 py-8 text-center">No recent alerts 🎉</div>')

    content = ('<div class="flex items-baseline justify-between mb-6">'
               '<h1 class="font-disp text-2xl font-bold text-slate-100 tracking-tight">Fleet Overview</h1>'
               '<span class="text-xs text-slate-500">auto-refresh 60s</span></div>'
               + band
               + '<div class="grid grid-cols-1 xl:grid-cols-3 gap-6">'
               '<div class="xl:col-span-2">' + _section_title("Hosts", str(len(hosts_data)) + " managed") + host_grid + "</div>"
               '<div>' + _section_title("Recent Alerts") + '<div class="rounded-xl border border-ink-700/60 bg-ink-900/60 shadow-tile p-5">'
               + alerts_html + "</div></div></div>")

    extra = ('<script>setTimeout(function(){location.reload();},60000);</script>')
    return base_page(content, title="Dashboard", active="/", extra_scripts=extra)


# ---------------------------------------------------------------------------
# Hosts
# ---------------------------------------------------------------------------

def hosts_page(hosts_data: list) -> str:
    rows = ""
    for h in hosts_data:
        st = h.get("worst_status", "ok")
        tags = " ".join(_tag_chip(t) for t in h.get("tags", []))
        rows += ('<tr class="host-row hover:bg-ink-800/40 transition-colors" data-alias="' + _escape(str(h["alias"]))
                 + '" data-address="' + _escape(str(h.get("address", ""))) + '" data-status="' + st
                 + '" data-tags="' + _escape(",".join(h.get("tags", []))) + '">'
                 '<td class="px-3 py-2.5"><div class="flex items-center gap-2.5">' + status_dot(st, pulse=False)
                 + '<a class="font-medium text-slate-100 hover:text-acc transition-colors" href="/hosts/' + str(h["alias"]) + '">'
                 + _escape(str(h["alias"])) + "</a></div></td>"
                 '<td class="px-3 py-2.5 font-mono text-xs text-slate-400">' + _escape(str(h.get("address", ""))) + "</td>"
                 '<td class="px-3 py-2.5">' + badge(st) + "</td>"
                 '<td class="px-3 py-2.5"><div class="flex gap-1.5 flex-wrap">' + tags + "</div></td></tr>")
    body = rows or _empty("No hosts found", 4)

    filters = ('<div class="flex flex-wrap gap-2.5 mb-4">'
               '<input id="host-search" type="text" placeholder="Search alias or address…" '
               'class="px-3 py-1.5 rounded-lg bg-ink-900/70 border border-ink-700/60 text-[13px] text-slate-200 placeholder-slate-600 focus:outline-none focus:border-acc/50 focus:ring-1 focus:ring-acc/30 w-56">'
               '<select id="host-filter-status" class="px-3 py-1.5 rounded-lg bg-ink-900/70 border border-ink-700/60 text-[13px] text-slate-300 focus:outline-none focus:border-acc/50">'
               '<option value="">All status</option><option value="ok">OK</option><option value="warn">WARN</option><option value="crit">CRIT</option></select>'
               '<select id="host-filter-tag" class="px-3 py-1.5 rounded-lg bg-ink-900/70 border border-ink-700/60 text-[13px] text-slate-300 focus:outline-none focus:border-acc/50">'
               '<option value="">All tags</option></select></div>')

    content = ('<h1 class="font-disp text-2xl font-bold text-slate-100 tracking-tight mb-6">Hosts</h1>'
               + filters + _table(["Host", "Address", "Status", "Tags"], body))

    js = ('<script>\n'
          '(function(){var tags=new Set();document.querySelectorAll(".host-row").forEach(function(r){r.dataset.tags.split(",").forEach(function(t){if(t)tags.add(t);});});'
          'var sel=document.getElementById("host-filter-tag");tags.forEach(function(t){var o=document.createElement("option");o.value=t;o.textContent=t;sel.appendChild(o);});'
          'function apply(){var q=document.getElementById("host-search").value.toLowerCase();'
          'var st=document.getElementById("host-filter-status").value;var tg=document.getElementById("host-filter-tag").value;'
          'document.querySelectorAll(".host-row").forEach(function(r){var mQ=!q||r.dataset.alias.toLowerCase().includes(q)||r.dataset.address.toLowerCase().includes(q);'
          'var mS=!st||r.dataset.status===st;var mT=!tg||r.dataset.tags.split(",").includes(tg);r.style.display=(mQ&&mS&&mT)?"":"none";});}'
          'document.getElementById("host-search").addEventListener("input",apply);'
          'document.getElementById("host-filter-status").addEventListener("change",apply);'
          'document.getElementById("host-filter-tag").addEventListener("change",apply);})();\n'
          '</script>')
    return base_page(content, title="Hosts", active="/hosts", extra_scripts=js)


# ---------------------------------------------------------------------------
# Host detail
# ---------------------------------------------------------------------------

def host_detail_page(alias: str, inspections: list, trend_html: str = "") -> str:
    rows = ""
    for i in inspections:
        rows += ('<tr class="hover:bg-ink-800/40 transition-colors">'
                 '<td class="px-3 py-2.5 font-mono text-xs text-slate-500">' + _escape(str(i.get("ts", ""))[:19]) + "</td>"
                 '<td class="px-3 py-2.5 text-slate-300">' + _escape(str(i.get("check_name", ""))) + "</td>"
                 '<td class="px-3 py-2.5">' + badge(i.get("status", "")) + "</td>"
                 '<td class="px-3 py-2.5 font-mono text-xs text-slate-400">' + _escape(_format_value(i.get("value"))) + "</td>"
                 '<td class="px-3 py-2.5"><button class="toggle-raw text-[11px] font-mono text-acc/80 hover:text-acc transition-colors">'
                 'raw</button><pre class="raw-output hidden mt-2 mb-1 font-mono text-[11px] text-slate-400 bg-ink-950 border border-ink-700/60 rounded-lg p-3 overflow-x-auto max-h-56 overflow-y-auto scroll-slim">'
                 + _escape(i.get("raw_stdout", "")) + "</pre></td></tr>")
    body = rows or _empty("No inspection history", 5)

    content = ('<div class="flex items-center gap-3 mb-1"><a href="/hosts" class="text-slate-500 hover:text-acc transition-colors text-sm">← hosts</a>'
               '<span class="text-slate-600">/</span>'
               '<h1 class="font-disp text-2xl font-bold text-slate-100 tracking-tight">' + _escape(str(alias)) + "</h1></div>"
               '<div class="text-xs text-slate-500 mb-6 font-mono">host detail &amp; inspection history</div>'
               '<div id="host-trend-chart"></div>'
               + _section_title("Recent Inspections") + _table(["Time", "Check", "Status", "Value", "Output"], body))

    js = ('<script>\n'
          'document.querySelectorAll(".toggle-raw").forEach(function(b){b.addEventListener("click",function(){b.nextElementSibling.classList.toggle("hidden");});});\n'
          'fetch("/api/hosts/"+encodeURIComponent(window.location.pathname.split("/").pop())+"/trends?days=7")'
          '.then(function(r){return r.json();}).then(function(data){'
          'var keys=Object.keys(data);if(!keys.length)return;'
          'var html=\'<div class="mb-8"><div class="flex items-baseline gap-3 mb-4"><h2 class="font-disp text-lg font-semibold text-slate-100">Trends</h2><span class="text-xs text-slate-500">7 days</span></div><div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">\';'
          'keys.forEach(function(k){var d=data[k];if(d.points.length<2)return;'
          'var vals=d.points.map(function(p){return p.value;});var first=vals[0],last=vals[vals.length-1];var delta=last-first;'
          'var color=delta>0?"#f87171":"#34d399";'
          'html+=\'<div class="rounded-xl border border-ink-700/60 bg-ink-900/60 shadow-tile p-4 rise"><div class="text-[11px] uppercase tracking-wider text-slate-500 mb-2 font-mono">\'+k+"</div>"'
          '+\'<div class="font-disp text-xl font-semibold text-slate-100">\'+last+"</div>"'
          '+\'<div class="text-xs font-mono mt-1" style="color:\'+color+\'">\'+(delta>0?"▲ +":"▼ ")+delta.toFixed(1)+" vs 7d ago</div></div>";});'
          'html+="</div></div>";document.getElementById("host-trend-chart").innerHTML=html;'
          '}).catch(function(){});\n'
          '</script>')
    return base_page(content, title=str(alias), active="/hosts", extra_scripts=js)


# ---------------------------------------------------------------------------
# Inspections
# ---------------------------------------------------------------------------

def inspections_page(hosts: list, checks: list, inspections: list) -> str:
    host_opts = "".join('<option value="' + _escape(str(h)) + '">' + _escape(str(h)) + "</option>" for h in hosts)
    check_opts = "".join('<option value="' + _escape(str(c)) + '">' + _escape(str(c)) + "</option>" for c in checks)

    def row(i):
        return ('<tr class="hover:bg-ink-800/40 transition-colors">'
                '<td class="px-3 py-2.5 font-mono text-xs text-slate-500">' + _escape(str(i.get("ts", ""))[:19]) + "</td>"
                '<td class="px-3 py-2.5"><a class="text-slate-200 hover:text-acc transition-colors" href="/hosts/' + str(i.get("host", "")) + '">'
                + _escape(str(i.get("host", ""))) + "</a></td>"
                '<td class="px-3 py-2.5 text-slate-300">' + _escape(str(i.get("check_name", ""))) + "</td>"
                '<td class="px-3 py-2.5">' + badge(i.get("status", "")) + "</td>"
                '<td class="px-3 py-2.5 font-mono text-xs text-slate-400">' + _escape(_format_value(i.get("value"))) + "</td></tr>")

    body = "".join(row(i) for i in inspections) or _empty("No inspections found", 5)

    sel = ('class="px-3 py-1.5 rounded-lg bg-ink-900/70 border border-ink-700/60 text-[13px] text-slate-300 focus:outline-none focus:border-acc/50"')
    filters = ('<div class="flex flex-wrap gap-2.5 mb-4">'
               '<select id="fhost" ' + sel + '><option value="">All hosts</option>' + host_opts + "</select>"
               '<select id="fcheck" ' + sel + '><option value="">All checks</option>' + check_opts + "</select>"
               '<select id="fstatus" ' + sel + '><option value="">All status</option><option value="ok">OK</option>'
               '<option value="warn">WARN</option><option value="crit">CRIT</option></select>'
               '<button onclick="applyFilters()" class="px-4 py-1.5 rounded-lg bg-acc/90 hover:bg-acc text-ink-950 text-[13px] font-semibold transition-colors">Filter</button></div>')

    content = ('<h1 class="font-disp text-2xl font-bold text-slate-100 tracking-tight mb-6">Inspections</h1>'
               + filters + _table(["Time", "Host", "Check", "Status", "Value"], body))

    js = ('<script>\n'
          'function applyFilters(){var p=new URLSearchParams();'
          'var h=document.getElementById("fhost").value;if(h)p.set("host",h);'
          'var c=document.getElementById("fcheck").value;if(c)p.set("check",c);'
          'var s=document.getElementById("fstatus").value;if(s)p.set("status",s);p.set("limit","200");'
          'fetch("/api/inspections?"+p).then(function(r){return r.json();}).then(function(data){'
          'var tb=document.querySelector("tbody");'
          'tb.innerHTML=data.length?data.map(function(i){return \'<tr class="hover:bg-ink-800/40"><td class="px-3 py-2.5 font-mono text-xs text-slate-500">\'+(i.ts||"").slice(0,19)+\'</td><td class="px-3 py-2.5 text-slate-200">\'+i.host+\'</td><td class="px-3 py-2.5 text-slate-300">\'+i.check_name+\'</td><td class="px-3 py-2.5">\'+"BADGE"+\'</td><td class="px-3 py-2.5 font-mono text-xs text-slate-400">\'+JSON.stringify(i.value)+\'</td></tr>\';}).join(""):\'<tr><td colspan="5" class="px-3 py-12 text-center text-sm text-slate-500">No inspections found</td></tr>\';'
          '});}\n'
          '</script>')
    # badge() is server-side; for the client-side re-render we inline a small JS badge fn
    js = js.replace('"BADGE"', 'badgeJs(i.status)')
    js = js.replace('function applyFilters()',
                    'function badgeJs(st){var c={ok:"#34d399",warn:"#fbbf24",crit:"#f87171"}[st]||"#94a3b8";'
                    'return \'<span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-mono border" style="color:\'+c+\';background:\'+c+\'14;border-color:\'+c+\'33"><span class="w-1.5 h-1.5 rounded-full" style="background:\'+c+\'"></span>\'+st.toUpperCase()+"</span>";}\n'
                    'function applyFilters()')
    return base_page(content, title="Inspections", active="/inspections", extra_scripts=js)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def audit_page(rows: list) -> str:
    if not rows:
        body = _empty("No audit records found", 7)
    else:
        verdict_style = {
            "auto_allow": ("text-ok", "✓"),
            "approved": ("text-acc", "✓"),
            "denied": ("text-crit", "✕"),
        }
        body = ""
        for r in rows:
            v = str(r.get("verdict", ""))
            vc, mark = verdict_style.get(v, ("text-slate-400", "·"))
            body += ('<tr class="hover:bg-ink-800/40 transition-colors">'
                     '<td class="px-3 py-2.5 font-mono text-xs text-slate-500">' + _escape(str(r.get("ts", ""))[:19]) + "</td>"
                     '<td class="px-3 py-2.5 text-slate-300">' + _escape(str(r.get("host", ""))) + "</td>"
                     '<td class="px-3 py-2.5 font-mono text-xs text-slate-300 max-w-xs truncate">' + _escape(str(r.get("command", ""))) + "</td>"
                     '<td class="px-3 py-2.5 font-mono text-xs text-slate-400">' + _escape(str(r.get("rc", ""))) + "</td>"
                     '<td class="px-3 py-2.5 font-mono text-xs ' + vc + '">' + mark + " " + _escape(v) + "</td>"
                     '<td class="px-3 py-2.5 text-xs text-slate-500">' + _escape(str(r.get("initiated_by", ""))) + "</td>"
                     '<td class="px-3 py-2.5 text-xs text-slate-500">' + _escape(str(r.get("approved_by", ""))) + "</td></tr>")

    filters = ('<div class="flex flex-wrap gap-2.5 mb-4">'
               '<select id="audit-filter-verdict" class="px-3 py-1.5 rounded-lg bg-ink-900/70 border border-ink-700/60 text-[13px] text-slate-300 focus:outline-none focus:border-acc/50">'
               '<option value="">All verdicts</option><option value="auto_allow">Auto allow</option>'
               '<option value="approved">Approved</option><option value="denied">Denied</option></select></div>')

    content = ('<h1 class="font-disp text-2xl font-bold text-slate-100 tracking-tight mb-6">Command Audit</h1>'
               + filters + _table(["Time", "Host", "Command", "RC", "Verdict", "By", "Approved by"], body))

    js = ('<script>\n'
          'document.getElementById("audit-filter-verdict").addEventListener("change",function(){var v=this.value;'
          'document.querySelectorAll("tbody tr").forEach(function(r){if(!v){r.style.display="";return;}'
          'var cell=(r.cells[4].textContent||"").trim().toLowerCase().replace(/\\s+/g,"_");'
          'r.style.display=(cell===v||cell.indexOf(v)>=0)?"":"none";});});\n'
          '</script>')
    return base_page(content, title="Audit", active="/audit", extra_scripts=js)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def config_page(info: dict) -> str:
    checks = "".join('<span class="px-2 py-0.5 rounded-md text-[11px] font-mono text-acc bg-acc-soft border border-acc/20">'
                     + _escape(str(c)) + "</span>" for c in info.get("checks", []))
    cards = ('<div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">'
             '<div class="rounded-xl border border-ink-700/60 bg-ink-900/60 shadow-tile p-5 rise">'
             '<div class="font-disp text-2xl font-bold text-acc">' + _escape(str(info.get("version", "?"))) + "</div>"
             '<div class="text-[10px] uppercase tracking-[0.14em] text-slate-500 mt-1.5">version</div></div>'
             '<div class="rounded-xl border border-ink-700/60 bg-ink-900/60 shadow-tile p-5 rise">'
             '<div class="font-disp text-2xl font-bold text-slate-100">' + str(info.get("hosts", 0)) + "</div>"
             '<div class="text-[10px] uppercase tracking-[0.14em] text-slate-500 mt-1.5">managed hosts</div></div>'
             '<div class="rounded-xl border border-ink-700/60 bg-ink-900/60 shadow-tile p-5 rise">'
             '<div class="font-disp text-2xl font-bold text-slate-100">' + str(len(info.get("checks", []))) + "</div>"
             '<div class="text-[10px] uppercase tracking-[0.14em] text-slate-500 mt-1.5">built-in checks</div></div></div>')
    checks_panel = ('<div class="rounded-xl border border-ink-700/60 bg-ink-900/60 shadow-tile p-5">'
                    + _section_title("Built-in Checks") + '<div class="flex flex-wrap gap-1.5">' + checks + "</div></div>")
    content = ('<h1 class="font-disp text-2xl font-bold text-slate-100 tracking-tight mb-6">Configuration</h1>'
               + cards + checks_panel)
    return base_page(content, title="Config", active="/config")


# ---------------------------------------------------------------------------
# Chat — agent panel
# ---------------------------------------------------------------------------

def chat_page() -> str:
    content = ('<div class="flex flex-col h-[calc(100vh-7.5rem)]">'
               '<div class="flex items-center justify-between mb-4">'
               '<div><h1 class="font-disp text-2xl font-bold text-slate-100 tracking-tight">Agent</h1>'
               '<p class="text-xs text-slate-500 mt-0.5">natural-language ops · tool calls are shown inline · remote commands need your approval</p></div>'
               '<span id="chat-session" class="font-mono text-[11px] text-slate-600"></span></div>'
               '<div class="flex-1 flex flex-col rounded-xl border border-ink-700/60 bg-ink-900/50 shadow-tile overflow-hidden">'
               '<div id="msgs" class="flex-1 overflow-y-auto scroll-slim px-5 py-5 space-y-4">'
               '<div class="text-center py-10 max-w-md mx-auto">'
               '<div class="w-12 h-12 mx-auto mb-4 rounded-xl bg-acc-soft border border-acc/20 flex items-center justify-center text-acc">' + _icon("chat") + '</div>'
               '<div class="font-disp text-slate-200 text-base mb-1">Ask the agent about your fleet</div>'
               '<div class="text-xs text-slate-500 mb-5 leading-relaxed">read-only checks run automatically · anything that changes a host pauses for your approval</div>'
               '<div class="flex flex-wrap gap-2 justify-center">'
               + "".join('<button onclick="suggest(\'' + q + '\')" class="px-3 py-1.5 rounded-full text-xs font-mono border border-ink-700/70 bg-ink-800/60 text-slate-400 hover:text-acc hover:border-acc/40 transition-colors">' + q + "</button>"
                         for q in ["list all hosts", "check disk usage", "any failed services?", "show recent alerts"])
               + "</div></div>"
               '</div>'
               '<div class="border-t border-ink-700/60 bg-ink-850/60 px-4 py-3 flex gap-2.5">'
               '<input id="chat-input" placeholder="Ask about your fleet…" autofocus '
               'class="flex-1 bg-ink-950/80 border border-ink-700/60 rounded-lg px-3.5 py-2.5 text-[14px] text-slate-100 placeholder-slate-600 focus:outline-none focus:border-acc/50 focus:ring-1 focus:ring-acc/30 font-body">'
               '<button onclick="sendMsg()" class="px-5 py-2.5 rounded-lg bg-acc/90 hover:bg-acc text-ink-950 text-[13px] font-semibold transition-colors">Send</button>'
               '</div></div></div>')

    js = ('<style>.spinner{width:13px;height:13px;border:2px solid #2a3d66;border-top-color:#38bdf8;border-radius:99px;animation:spin .7s linear infinite;flex-shrink:0}'
          '@keyframes spin{to{transform:rotate(360deg)}}</style>\n'
          '<script>\n' + _CHAT_JS + '\n</script>')
    extra_head = ('<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>'
                  '<script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>'
                  '<style>.md{word-break:break-word}'
                  '.md p{margin:.35em 0}.md p:first-child{margin-top:0}.md p:last-child{margin-bottom:0}'
                  '.md table{border-collapse:collapse;width:100%;margin:.5em 0;font-size:12.5px}'
                  '.md th,.md td{border:1px solid #1d2c4d;padding:4px 9px;text-align:left}'
                  '.md th{background:#0d1526;color:#7dd3fc;font-weight:600}'
                  '.md tr:nth-child(even) td{background:rgba(255,255,255,.015)}'
                  '.md code{font-family:"JetBrains Mono",monospace;background:#080d18;border:1px solid #1d2c4d;border-radius:4px;padding:1px 5px;font-size:12px;color:#7dd3fc}'
                  '.md pre{background:#080d18;border:1px solid #1d2c4d;border-radius:8px;padding:10px 12px;overflow-x:auto;margin:.5em 0}'
                  '.md pre code{background:none;border:none;padding:0;color:#cbd5e1}'
                  '.md ul,.md ol{margin:.4em 0 .4em 1.3em}.md li{margin:.15em 0}'
                  '.md strong{color:#e2e8f0}.md h1,.md h2,.md h3{color:#e2e8f0;margin:.6em 0 .3em;font-family:"Space Grotesk",sans-serif}'
                  '.md a{color:#38bdf8}</style>')
    return base_page(content, title="Chat", active="/chat",
                     extra_head=extra_head, extra_scripts=js)


# Chat JS — SSE streaming, tool-call trace cards, inline approval. Plain string.
_CHAT_JS = """
var sessionId=null;
var msgs=document.getElementById('msgs');
var lastTool=null;
function suggest(t){var i=document.getElementById('chat-input');i.value=t;i.focus();}
function esc(s){var d=document.createElement('div');d.textContent=(s==null?'':s);return d.innerHTML;}
function scrollBottom(){msgs.scrollTop=msgs.scrollHeight;}
function addNode(html){var t=document.createElement('div');t.innerHTML=html.trim();var n=t.firstChild;msgs.appendChild(n);scrollBottom();return n;}
function clearHint(){var h=msgs.querySelector('.text-center');if(h)h.remove();}
function showTyping(){hideTyping();typing=addNode('<div class="typing flex items-center pl-1"><i></i><i></i><i></i></div>');}
var typing=null;
function hideTyping(){if(typing){typing.remove();typing=null;}}
function sendMsg(){
  var inp=document.getElementById('chat-input');
  var text=inp.value.trim(); if(!text)return;
  clearHint();
  addNode('<div class="flex justify-end rise"><div class="max-w-[75%] rounded-2xl rounded-br-sm bg-acc-soft border border-acc/25 px-4 py-2.5 text-[14px] text-slate-100">'+esc(text)+'</div></div>');
  inp.value='';
  showTyping();
  var params=new URLSearchParams({message:text});
  if(sessionId)params.set('session_id',sessionId);
  var es=new EventSource('/api/chat?'+params);
  es.addEventListener('session',function(e){sessionId=e.data;var el=document.getElementById('chat-session');if(el)el.textContent='session '+e.data;});
  es.addEventListener('text',function(e){
    hideTyping();
    var body=(window.marked&&window.DOMPurify)?DOMPurify.sanitize(marked.parse(e.data)):esc(e.data);
    addNode('<div class="flex rise"><div class="md max-w-[85%] rounded-2xl rounded-bl-sm bg-ink-800/80 border border-ink-700/60 px-4 py-2.5 text-[14px] leading-relaxed text-slate-200">'+body+'</div></div>');
  });
  es.addEventListener('tool_use',function(e){
    hideTyping();
    lastTool=addNode('<div class="rise max-w-[85%] rounded-lg border border-ink-700/60 bg-ink-950/70 overflow-hidden">'
      +'<div class="tool-head flex items-center gap-2.5 px-3 py-2 text-xs font-mono text-slate-400"><span class="spinner"></span><span>'+esc(e.data)+'</span></div>'
      +'<div class="tool-body hidden border-t border-ink-700/50 px-3 py-2 text-xs font-mono text-ok/90 whitespace-pre-wrap"></div></div>');
  });
  es.addEventListener('tool_result',function(e){
    if(lastTool){
      var head=lastTool.querySelector('.tool-head');
      if(head){head.className='tool-head flex items-center gap-2.5 px-3 py-2 text-xs font-mono text-ok';
        var sp=head.querySelector('.spinner');if(sp)sp.outerHTML='<span>✓</span>';}
      var body=lastTool.querySelector('.tool-body');
      if(body){body.textContent=e.data;body.classList.remove('hidden');}
    }
    lastTool=null;
  });
  es.addEventListener('approval_required',function(e){
    hideTyping();
    addNode('<div class="rise max-w-[85%] rounded-xl border border-warn/40 bg-warn-soft p-4">'
      +'<div class="flex items-center gap-2 mb-2.5 text-warn text-[11px] font-mono uppercase tracking-wider">⚠ approval required · run_remote</div>'
      +'<pre class="font-mono text-[13px] text-slate-100 bg-ink-950 border border-ink-700/60 rounded-lg px-3.5 py-2.5 overflow-x-auto mb-3.5">'+esc(e.data)+'</pre>'
      +'<div class="flex gap-2.5">'
      +'<button onclick="resolveApproval(true,this)" class="px-4 py-1.5 rounded-lg bg-ok/90 hover:bg-ok text-ink-950 text-[13px] font-semibold transition-colors">Approve</button>'
      +'<button onclick="resolveApproval(false,this)" class="px-4 py-1.5 rounded-lg bg-crit/90 hover:bg-crit text-white text-[13px] font-semibold transition-colors">Deny</button>'
      +'</div></div>');
  });
  es.addEventListener('error',function(e){
    hideTyping();
    addNode('<div class="rise text-crit text-[13px] font-mono px-1">connection error — is the API key set?</div>');
    es.close();
  });
  es.addEventListener('done',function(e){hideTyping();es.close();});
}
function resolveApproval(approved,btn){
  var card=btn.closest('.rounded-xl');
  card.querySelectorAll('button').forEach(function(b){b.disabled=true;b.classList.add('opacity-40','cursor-not-allowed');});
  var tag=approved?'<span class="text-ok font-mono text-xs">✓ approved</span>':'<span class="text-crit font-mono text-xs">✕ denied</span>';
  card.querySelector('.flex.gap-2\\.5').innerHTML=tag;
  if(sessionId)fetch('/api/chat/'+sessionId+'/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approved:approved})});
}
document.getElementById('chat-input').addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}});
"""

