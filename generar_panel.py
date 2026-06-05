#!/usr/bin/env python3
"""
Generador de panel de trading para GitHub Pages.
Corre en GitHub Actions: lee los estados de los bots via API de GitHub
(funciona con repos privados usando el token) y genera index.html.

Escalable: agrega bots a la lista BOTS y aparecen automaticamente.
"""
import urllib.request, json, base64, os
from datetime import datetime

OWNER = "ricardobarcelogoico-stack"
TOKEN = os.environ.get("GH_TOKEN", "")

# ============================================================
#  CONFIGURACION DE BOTS — agrega aqui cualquier bot nuevo
# ============================================================
BOTS = [
    {"nombre":"ORB", "repo":"bot-orb", "archivo":"estado_orb.json",
     "tipo":"single", "fase":"validacion"},
    {"nombre":"Fibonacci GLD", "repo":"fib-gld-bot", "archivo":"estado_fib_gld.json",
     "tipo":"single", "fase":"validacion"},
    {"nombre":"Fibonacci QQQ", "repo":"bot-validacion", "archivo":"estado_validacion.json",
     "tipo":"multi", "fase":"validacion", "info":"referencia"},
    # === Cuando pases a Apex real, descomenta y ajusta: ===
    # {"nombre":"Fibonacci Apex", "repo":"apex-fib-1", "archivo":"estado_fib_gld.json",
    #  "tipo":"single", "fase":"apex", "cuenta":"150K EOD"},
    # {"nombre":"ORB Apex", "repo":"apex-orb-1", "archivo":"estado_orb.json",
    #  "tipo":"single", "fase":"apex", "cuenta":"150K EOD"},
]

CAPITAL = 150000
APEX_DD = 4000
APEX_DAILY = 2000
APEX_CONSISTENCY = 4500
APEX_TARGET = 9000
META_OPS = 15
META_WR = 45

def fetch_estado(repo, archivo):
    """Lee un archivo de estado de un repo via API de GitHub."""
    url = f"https://api.github.com/repos/{OWNER}/{repo}/contents/{archivo}"
    req = urllib.request.Request(url)
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        contenido = base64.b64decode(data["content"]).decode()
        return json.loads(contenido)
    except Exception as e:
        print(f"  No se pudo leer {repo}/{archivo}: {e}")
        return None

def extraer_trades(estado, tipo):
    if estado is None: return []
    hist = estado.get("historial_global", []) if tipo == "multi" else estado.get("historial", [])
    out = []
    for t in hist:
        out.append({
            "ganancia": t.get("ganancia", 0),
            "retorno": t.get("retorno", 0),
            "razon": t.get("razon", ""),
            "fecha": t.get("fecha", ""),
            "symbol": t.get("symbol", estado.get("symbol", "—")),
            "posicion": t.get("posicion", ""),
        })
    return out

def calc_metricas(trades):
    if not trades:
        return {"ops":0,"wr":0,"pf":0,"ganancia":0,"max_dd":0,"wins":0,"losses":0,
                "mejor_dia":0,"peor_dia":0,"viola_consist":False,"viola_daily":False}
    rets=[t["retorno"] for t in trades]; gans=[t["ganancia"] for t in trades]
    wins=[r for r in rets if r>0]; losses=[r for r in rets if r<0]
    wr=len(wins)/len(rets)*100 if rets else 0
    suma_w=sum(g for g in gans if g>0); suma_l=abs(sum(g for g in gans if g<0))
    pf=suma_w/(suma_l+1e-10) if suma_l>0 else (99 if suma_w>0 else 0)
    ganancia=sum(gans)
    eq=CAPITAL; peak=CAPITAL; mdd=0
    for g in gans:
        eq+=g
        if eq>peak: peak=eq
        if peak-eq>mdd: mdd=peak-eq
    dias={}
    for t in trades:
        d=t["fecha"][:10] if t["fecha"] else "?"
        dias[d]=dias.get(d,0)+t["ganancia"]
    mejor=max(dias.values()) if dias else 0
    peor=min(dias.values()) if dias else 0
    return {"ops":len(trades),"wr":wr,"pf":pf,"ganancia":ganancia,"max_dd":mdd,
            "wins":len(wins),"losses":len(losses),"mejor_dia":mejor,"peor_dia":peor,
            "viola_consist":mejor>=APEX_CONSISTENCY,
            "viola_daily":abs(peor)>=APEX_DAILY if peor<0 else False}

def posicion_abierta(estado, tipo):
    if estado is None: return []
    activas=[]
    if tipo=="multi":
        for sym,inst in estado.get("instrumentos",{}).items():
            if inst.get("posicion"):
                activas.append(f"{sym} {inst['posicion']} @ ${inst.get('precio_entrada',0):,.2f}")
    else:
        if estado.get("posicion"):
            activas.append(f"{estado.get('symbol','—')} {estado['posicion']} @ ${estado.get('precio_entrada',0):,.2f}")
    return activas

def estado_cuenta_apex(met, estado):
    """Determina el estado de una cuenta Apex real."""
    if estado and estado.get("eval_pasada"):
        return ("pasada", "🎉 PASADA")
    if met["max_dd"] >= APEX_DD:
        return ("quemada", "🔴 QUEMADA")
    return ("activa", "🟢 ACTIVA")

# ============ RECOLECTAR ============
print("Leyendo estados de los bots...")
datos=[]
for b in BOTS:
    estado=fetch_estado(b["repo"], b["archivo"])
    trades=extraer_trades(estado, b["tipo"])
    met=calc_metricas(trades)
    activas=posicion_abierta(estado, b["tipo"])
    datos.append({**b, "met":met, "activas":activas, "estado":estado, "trades":trades})
    print(f"  {b['nombre']}: {met['ops']} ops, WR {met['wr']:.0f}%")

val = [d for d in datos if d["fase"]=="validacion"]
apex = [d for d in datos if d["fase"]=="apex"]

# Combinado validacion
v_ops=sum(d["met"]["ops"] for d in val)
v_wins=sum(d["met"]["wins"] for d in val)
v_wr=v_wins/v_ops*100 if v_ops>0 else 0
v_gan=sum(d["met"]["ganancia"] for d in val)

if v_ops>=META_OPS:
    if v_wr>=META_WR: sem=("verde","LUZ VERDE PARA APEX","El edge se sostiene en vivo")
    else: sem=("rojo","POSIBLE OVERFITTING",f"WR {v_wr:.0f}% bajo el minimo de {META_WR}%")
else:
    sem=("ambar","ACUMULANDO DATOS",f"Faltan {META_OPS-v_ops} operaciones para concluir")


def tabla_trades(trades, bot_id):
    if not trades: return ""
    rows = ""
    for i, t in enumerate(reversed(trades)):
        num = len(trades) - i
        gan = t["ganancia"]
        gan_color = "#2ee6a0" if gan >= 0 else "#ff5c6c"
        razon = t.get("razon", "")
        if "Take" in razon or "TP" in razon: cierre,cierre_c = "TP ✅","#2ee6a0"
        elif "Stop" in razon or "SL" in razon: cierre,cierre_c = "SL ❌","#ff5c6c"
        else: cierre,cierre_c = "EOD 🕐","#7a8699"
        pos = t.get("posicion","")
        dir_icon = "▲" if pos=="LONG" else ("▼" if pos=="SHORT" else "—")
        dir_color = "#2ee6a0" if pos=="LONG" else ("#ff5c6c" if pos=="SHORT" else "#7a8699")
        fecha = t["fecha"][:10] if t.get("fecha") else "—"
        rows += f'<tr><td style="color:#7a8699">{num}</td><td>{fecha}</td><td style="color:{dir_color}">{dir_icon} {pos}</td><td style="color:{cierre_c}">{cierre}</td><td style="color:{gan_color}">${gan:+,.0f}</td></tr>'
    return f'''<div class="trades-toggle" onclick="toggleTrades(\'trades-{bot_id}\')" id="btn-trades-{bot_id}">Ver operaciones ▾</div>
    <div class="trades-wrap" id="trades-{bot_id}" style="display:none">
      <table class="trades-tbl">
        <thead><tr><th>#</th><th>Fecha</th><th>Dir</th><th>Cierre</th><th>P&L</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>'''

def barra(pct,color):
    pct=max(0,min(100,pct))
    return f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div>'

def card_validacion(d, idx=0):
    m=d["met"]
    if d["activas"]:
        chips="".join(f'<span class="pos-chip">{a}</span>' for a in d["activas"])
        pos=f'<div class="pos-row"><span class="pos-label">ABIERTA</span>{chips}</div>'
    else:
        pos='<div class="pos-row"><span class="pos-label">ABIERTA</span><span class="pos-none">Sin posicion</span></div>'
    dd_pct=m["max_dd"]/APEX_DD*100
    dd_c="var(--green)" if dd_pct<60 else ("var(--amber)" if dd_pct<90 else "var(--red)")
    wr_c="var(--green)" if m["wr"]>=META_WR else "var(--amber)"
    gan_c="var(--green)" if m["ganancia"]>=0 else "var(--red)"
    cb='<span class="badge badge-bad">VIOLA CONSISTENCY</span>' if m["viola_consist"] else '<span class="badge badge-ok">CONSISTENCY OK</span>'
    db='<span class="badge badge-bad">VIOLA DAILY</span>' if m["viola_daily"] else '<span class="badge badge-ok">DAILY LOSS OK</span>'
    tbl = tabla_trades(d.get("trades",[]), f"{d['nombre'].replace(' ','-')}-{idx}")
    return f'''<div class="card">
      <div class="card-head"><h2>{d["nombre"]}</h2><span class="ops-count">{m["ops"]} ops</span></div>
      {pos}
      <div class="metrics-grid">
        <div class="metric"><span class="metric-label">WIN RATE</span><span class="metric-val" style="color:{wr_c}">{m["wr"]:.1f}%</span><span class="metric-sub">{m["wins"]}W / {m["losses"]}L</span></div>
        <div class="metric"><span class="metric-label">PROFIT FACTOR</span><span class="metric-val">{m["pf"]:.2f}</span><span class="metric-sub">{'rentable' if m["pf"]>1 else 'perdedor'}</span></div>
        <div class="metric"><span class="metric-label">GANANCIA SIM</span><span class="metric-val" style="color:{gan_c}">${m["ganancia"]:+,.0f}</span><span class="metric-sub">simulado</span></div>
        <div class="metric"><span class="metric-label">PEOR DD</span><span class="metric-val" style="color:{dd_c}">${m["max_dd"]:,.0f}</span><span class="metric-sub">limite ${APEX_DD:,}</span></div>
      </div>
      <div class="dd-section"><div class="dd-label"><span>Distancia al limite Apex DD</span><span>{dd_pct:.0f}%</span></div>{barra(dd_pct,dd_c)}</div>
      <div class="badges">{cb}{db}</div>
      {tbl}
    </div>'''

def card_apex(d):
    m=d["met"]; est=d["estado"]
    estado_cls, estado_txt = estado_cuenta_apex(m, est)
    ganancia = est.get("ganancia_total", m["ganancia"]) if est else m["ganancia"]
    target_pct = ganancia/APEX_TARGET*100
    falta = max(0, APEX_TARGET-ganancia)
    dd_pct=m["max_dd"]/APEX_DD*100
    dd_c="var(--green)" if dd_pct<60 else ("var(--amber)" if dd_pct<90 else "var(--red)")
    gan_dia = est.get("ganancia_hoy",0) if est else 0
    consist_pct = gan_dia/APEX_CONSISTENCY*100
    estado_color={"activa":"var(--green)","pasada":"var(--accent)","quemada":"var(--red)"}[estado_cls]
    if d["activas"]:
        chips="".join(f'<span class="pos-chip">{a}</span>' for a in d["activas"])
        pos=f'<div class="pos-row"><span class="pos-label">ABIERTA</span>{chips}</div>'
    else:
        pos='<div class="pos-row"><span class="pos-label">ABIERTA</span><span class="pos-none">Sin posicion</span></div>'
    return f'''<div class="card card-apex">
      <div class="card-head">
        <div><h2>{d["nombre"]}</h2><span class="cuenta-tag">{d.get("cuenta","Apex")}</span></div>
        <span class="estado-badge" style="background:{estado_color}1a;color:{estado_color}">{estado_txt}</span>
      </div>
      {pos}
      <div class="target-section">
        <div class="dd-label"><span>Progreso al target</span><span>${ganancia:+,.0f} / ${APEX_TARGET:,}</span></div>
        {barra(target_pct,'var(--green)' if target_pct>=0 else 'var(--red)')}
        <span class="falta-txt">{'¡Target alcanzado!' if falta==0 else f'Faltan ${falta:,.0f}'}</span>
      </div>
      <div class="metrics-grid">
        <div class="metric"><span class="metric-label">WIN RATE</span><span class="metric-val">{m["wr"]:.1f}%</span><span class="metric-sub">{m["ops"]} ops</span></div>
        <div class="metric"><span class="metric-label">PROFIT FACTOR</span><span class="metric-val">{m["pf"]:.2f}</span><span class="metric-sub">{'rentable' if m["pf"]>1 else '—'}</span></div>
      </div>
      <div class="dd-section"><div class="dd-label"><span>DD actual</span><span style="color:{dd_c}">${m["max_dd"]:,.0f} / ${APEX_DD:,}</span></div>{barra(dd_pct,dd_c)}</div>
      <div class="dd-section"><div class="dd-label"><span>Ganancia hoy (consistency)</span><span>${gan_dia:+,.0f} / ${APEX_CONSISTENCY:,}</span></div>{barra(consist_pct,'var(--amber)' if consist_pct>85 else 'var(--accent)')}</div>
    </div>'''

sem_color={"verde":"var(--green)","ambar":"var(--amber)","rojo":"var(--red)"}[sem[0]]

# Seccion validacion
seccion_val=""
if val:
    cards_val="".join(card_validacion(d, i) for i, d in enumerate(val))
    seccion_val=f'''
    <div class="seccion-titulo"><span class="dot dot-val"></span>EN VALIDACION</div>
    <div class="verdict">
      <div class="light" style="background:{sem_color};box-shadow:0 0 24px {sem_color}"></div>
      <div class="verdict-txt"><h3>{sem[1]}</h3><p>{sem[2]}</p></div>
    </div>
    <div class="progress-block">
      <h4>Progreso hacia la decision</h4>
      <div class="prog-row"><div class="prog-label"><span>Operaciones acumuladas</span><span>{v_ops} / {META_OPS}</span></div>{barra(v_ops/META_OPS*100,'var(--accent)')}</div>
      <div class="prog-row"><div class="prog-label"><span>Win rate combinado</span><span>{v_wr:.1f}% / {META_WR}% min</span></div>{barra(v_wr/META_WR*100 if META_WR else 0,'var(--green)' if v_wr>=META_WR else 'var(--amber)')}</div>
      <div class="prog-row"><div class="prog-label"><span>Ganancia simulada combinada</span><span>${v_gan:+,.0f}</span></div></div>
    </div>
    <div class="grid">{cards_val}</div>'''

# Seccion Apex
seccion_apex=""
if apex:
    cards_apex="".join(card_apex(d) for d in apex)
    total_apex_gan=sum((d["estado"].get("ganancia_total",0) if d["estado"] else 0) for d in apex)
    seccion_apex=f'''
    <div class="seccion-titulo"><span class="dot dot-apex"></span>EN APEX REAL</div>
    <div class="apex-resumen">
      <span>Cuentas activas: <b>{len(apex)}</b></span>
      <span>Ganancia total: <b style="color:{'var(--green)' if total_apex_gan>=0 else 'var(--red)'}">${total_apex_gan:+,.0f}</b></span>
    </div>
    <div class="grid">{cards_apex}</div>'''
else:
    seccion_apex='''
    <div class="seccion-titulo"><span class="dot dot-apex"></span>EN APEX REAL</div>
    <div class="empty-apex">Todavia no hay cuentas Apex activas.<br>Cuando pases la validacion y arranques una cuenta, apareceran aqui automaticamente.</div>'''

ahora=datetime.now().strftime("%d %b %Y · %I:%M %p")

html=f'''<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panel de Trading</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#0a0e14;--panel:#121822;--panel-2:#1a2130;--line:#232c3d;--text:#e4e9f0;--muted:#7a8699;--green:#2ee6a0;--amber:#ffb547;--red:#ff5c6c;--accent:#4d9fff;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--bg);color:var(--text);font-family:'Sora',sans-serif;padding:24px 16px 60px;background-image:radial-gradient(circle at 20% 0%,rgba(77,159,255,0.06),transparent 40%),radial-gradient(circle at 90% 10%,rgba(46,230,160,0.05),transparent 35%);min-height:100vh;}}
.wrap{{max-width:1000px;margin:0 auto;}}
.top{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:28px;flex-wrap:wrap;gap:10px;}}
.top h1{{font-size:24px;font-weight:800;letter-spacing:-0.5px;}}
.top h1 span{{color:var(--accent);}}
.top .ts{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--muted);}}
.seccion-titulo{{display:flex;align-items:center;gap:9px;font-size:13px;font-weight:700;letter-spacing:1.5px;color:var(--muted);margin:30px 0 16px;text-transform:uppercase;}}
.seccion-titulo:first-child{{margin-top:0;}}
.dot{{width:9px;height:9px;border-radius:50%;}}
.dot-val{{background:var(--amber);}} .dot-apex{{background:var(--green);}}
.verdict{{background:linear-gradient(135deg,var(--panel),var(--panel-2));border:1px solid var(--line);border-radius:16px;padding:22px 26px;margin-bottom:20px;display:flex;align-items:center;gap:20px;position:relative;overflow:hidden;}}
.light{{width:48px;height:48px;border-radius:50%;flex-shrink:0;animation:pulse 2s infinite;}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.55}}}}
.verdict-txt h3{{font-size:19px;font-weight:700;}} .verdict-txt p{{color:var(--muted);font-size:13px;margin-top:3px;}}
.progress-block{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px 24px;margin-bottom:20px;}}
.progress-block h4{{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:15px;}}
.prog-row{{margin-bottom:16px;}} .prog-row:last-child{{margin-bottom:0;}}
.prog-label{{display:flex;justify-content:space-between;font-size:13px;margin-bottom:7px;}}
.prog-label span:last-child{{font-family:'IBM Plex Mono',monospace;}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;}}
@media (max-width:760px){{.grid{{grid-template-columns:1fr;}} .top h1{{font-size:20px;}}}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;}}
.card-apex{{border-color:rgba(46,230,160,0.2);}}
.card-head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:15px;}}
.card-head h2{{font-size:18px;font-weight:700;}}
.cuenta-tag{{font-size:11px;color:var(--muted);font-family:'IBM Plex Mono',monospace;}}
.ops-count{{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--muted);background:var(--panel-2);padding:4px 10px;border-radius:20px;}}
.estado-badge{{font-size:11px;font-weight:700;padding:5px 11px;border-radius:20px;letter-spacing:0.3px;}}
.pos-row{{display:flex;align-items:center;gap:10px;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--line);flex-wrap:wrap;}}
.pos-label{{font-size:10px;letter-spacing:1px;color:var(--muted);background:var(--panel-2);padding:3px 8px;border-radius:4px;}}
.pos-chip{{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--accent);background:rgba(77,159,255,0.1);padding:4px 10px;border-radius:6px;}}
.pos-none{{font-size:13px;color:var(--muted);}}
.metrics-grid{{display:grid;grid-template-columns:1fr 1fr;gap:13px;margin-bottom:16px;}}
.metric{{display:flex;flex-direction:column;gap:2px;}}
.metric-label{{font-size:10px;letter-spacing:0.8px;color:var(--muted);}}
.metric-val{{font-family:'IBM Plex Mono',monospace;font-size:23px;font-weight:600;}}
.metric-sub{{font-size:11px;color:var(--muted);}}
.target-section{{margin-bottom:16px;}}
.falta-txt{{font-size:11px;color:var(--muted);margin-top:6px;display:block;}}
.dd-section{{margin-bottom:13px;}}
.dd-label{{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-bottom:6px;}}
.dd-label span:last-child{{font-family:'IBM Plex Mono',monospace;}}
.bar-track{{height:7px;background:var(--panel-2);border-radius:6px;overflow:hidden;}}
.bar-fill{{height:100%;border-radius:6px;transition:width 0.6s;}}
.badges{{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px;}}
.badge{{font-size:10px;letter-spacing:0.5px;padding:5px 10px;border-radius:6px;font-weight:600;}}
.badge-ok{{background:rgba(46,230,160,0.12);color:var(--green);}}
.badge-bad{{background:rgba(255,92,108,0.12);color:var(--red);}}
.apex-resumen{{display:flex;gap:24px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 20px;margin-bottom:18px;font-size:13px;color:var(--muted);}}
.apex-resumen b{{color:var(--text);font-family:'IBM Plex Mono',monospace;}}
.empty-apex{{background:var(--panel);border:1px dashed var(--line);border-radius:14px;padding:30px;text-align:center;color:var(--muted);font-size:13px;line-height:1.7;}}
.footer{{text-align:center;margin-top:34px;font-size:11px;color:var(--muted);font-family:'IBM Plex Mono',monospace;line-height:1.7;}}
.footer b{{color:var(--text);}}
.refresh-note{{text-align:center;font-size:11px;color:var(--muted);margin-top:8px;}}
</style></head><body><div class="wrap">
  <div class="top"><h1>Panel de Trading <span>· Apex</span></h1><div class="ts">Actualizado: {ahora}</div></div>
  {seccion_val}
  {seccion_apex}
  <div class="footer">
    Criterio de decision: <b>{META_OPS}+ operaciones</b> con <b>WR combinado ≥ {META_WR}%</b> = luz verde Apex<br>
    Se actualiza automaticamente · Datos de validacion en vivo
  </div>
</div><script>
function toggleTrades(id) {
  var wrap = document.getElementById(id);
  var btn = document.getElementById('btn-' + id);
  if (wrap.style.display === 'none') {
    wrap.style.display = 'block';
    btn.innerHTML = 'Ocultar operaciones ▴';
  } else {
    wrap.style.display = 'none';
    btn.innerHTML = 'Ver operaciones ▾';
  }
}
</script>
</body></html>'''

with open("index.html","w") as f:
    f.write(html)
print("\nindex.html generado correctamente")
