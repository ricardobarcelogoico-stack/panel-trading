#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard de Trading completo para GitHub Pages.
Corre en Railway: lee estados de los 5 bots + memoria de Claude via API de GitHub
(repos privados con token) y genera + publica index.html.

Estilo: terminal de trading oscuro. Todo en una vista.
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
     "tipo":"single", "mercado":"QQQ → MNQ", "meta_ops":100, "color":"#4d9fff"},
    {"nombre":"Fibonacci GLD", "repo":"fib-gld-bot", "archivo":"estado_fib_gld.json",
     "tipo":"single", "mercado":"GLD → MGC", "meta_ops":50, "color":"#ffb547"},
    {"nombre":"VWAP Bounce", "repo":"bot-vwap-bounce", "archivo":"estado_vwap.json",
     "tipo":"single", "mercado":"QQQ", "meta_ops":50, "color":"#2ee6a0"},
    {"nombre":"RSI(2) Connors", "repo":"bot-rsi2-spy", "archivo":"estado_rsi2.json",
     "tipo":"single", "mercado":"SPY", "meta_ops":50, "color":"#c98bff"},
    {"nombre":"Asian Range", "repo":"bot-asian-range", "archivo":"estado_asian.json",
     "tipo":"single", "mercado":"EUR/USD", "meta_ops":50, "color":"#ff8fa3"},
    {"nombre":"Validacion Multi", "repo":"bot-validacion", "archivo":"estado_validacion.json",
     "tipo":"multi", "mercado":"varios", "meta_ops":50, "color":"#7a8699", "info":"referencia"},
]

CAPITAL = 150000
APEX_DD = 4000
META_WR = 45

# ============================================================
#  LECTURA DE DATOS
# ============================================================
def fetch_json(repo, archivo):
    url = f"https://api.github.com/repos/{OWNER}/{repo}/contents/{archivo}"
    req = urllib.request.Request(url)
    if TOKEN: req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        return json.loads(base64.b64decode(data["content"]).decode())
    except Exception as e:
        print(f"  No se pudo leer {repo}/{archivo}: {e}")
        return None

def extraer_trades(estado, tipo):
    if estado is None: return []
    hist = estado.get("historial_global", []) if tipo=="multi" else estado.get("historial", [])
    out = []
    for t in hist:
        out.append({
            "ganancia": t.get("ganancia", 0), "retorno": t.get("retorno", 0),
            "razon": t.get("razon", ""), "fecha": t.get("fecha", ""),
            "symbol": t.get("symbol", estado.get("symbol", "—")),
            "posicion": t.get("posicion", ""),
        })
    return out

def calc_metricas(trades):
    if not trades:
        return {"ops":0,"wr":0,"pf":0,"ganancia":0,"max_dd":0,"wins":0,"losses":0,
                "equity":[CAPITAL],"racha":0,"racha_tipo":""}
    rets=[t["retorno"] for t in trades]; gans=[t["ganancia"] for t in trades]
    wins=[r for r in rets if r>0]; losses=[r for r in rets if r<0]
    wr=len(wins)/len(rets)*100 if rets else 0
    suma_w=sum(g for g in gans if g>0); suma_l=abs(sum(g for g in gans if g<0))
    pf=suma_w/(suma_l+1e-10) if suma_l>0 else (99 if suma_w>0 else 0)
    ganancia=sum(gans)
    eq=CAPITAL; peak=CAPITAL; mdd=0; curve=[CAPITAL]
    for g in gans:
        eq+=g; curve.append(eq)
        if eq>peak: peak=eq
        if peak-eq>mdd: mdd=peak-eq
    # Racha actual
    racha=0; racha_tipo=""
    for g in reversed(gans):
        tipo_g = "W" if g>0 else "L"
        if racha==0: racha_tipo=tipo_g; racha=1
        elif tipo_g==racha_tipo: racha+=1
        else: break
    return {"ops":len(trades),"wr":wr,"pf":pf,"ganancia":ganancia,"max_dd":mdd,
            "wins":len(wins),"losses":len(losses),"equity":curve,
            "racha":racha,"racha_tipo":racha_tipo}

def posicion_abierta(estado, tipo):
    if estado is None: return []
    activas=[]
    if tipo=="multi":
        for sym,inst in estado.get("instrumentos",{}).items():
            if inst.get("posicion"):
                activas.append(f"{sym} {inst['posicion']} @ ${inst.get('precio_entrada',0):,.2f}")
    else:
        if estado.get("posicion"):
            sym = estado.get("symbol","—")
            pe = estado.get("precio_entrada",0)
            fmt = f"{pe:.5f}" if pe<10 else f"${pe:,.2f}"
            activas.append(f"{estado['posicion']} @ {fmt}")
    return activas

# ============================================================
#  ANALISIS DE CLAUDE
# ============================================================
def cargar_claude():
    mem = fetch_json("claude-brain", "memoria.json")
    pat = fetch_json("claude-brain", "patrones.json")
    return mem if mem else [], pat if pat else {}

# ============================================================
#  COMPONENTES VISUALES
# ============================================================
def sparkline(equity, color, w=260, h=48):
    """Genera un SVG sparkline de la equity curve."""
    if len(equity) < 2:
        return f'<svg width="{w}" height="{h}"></svg>'
    lo, hi = min(equity), max(equity)
    rng = hi-lo if hi>lo else 1
    pts = []
    for i,v in enumerate(equity):
        x = i/(len(equity)-1)*w
        y = h - (v-lo)/rng*(h-6) - 3
        pts.append(f"{x:.1f},{y:.1f}")
    path = "M" + " L".join(pts)
    fill_pts = pts + [f"{w},{h}", f"0,{h}"]
    fill = "M" + " L".join(fill_pts) + " Z"
    final_up = equity[-1] >= equity[0]
    c = color if final_up else "#ff5c6c"
    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none">
      <defs><linearGradient id="g{id(equity)}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="{c}" stop-opacity="0.25"/>
        <stop offset="100%" stop-color="{c}" stop-opacity="0"/></linearGradient></defs>
      <path d="{fill}" fill="url(#g{id(equity)})"/>
      <path d="{path}" fill="none" stroke="{c}" stroke-width="2" stroke-linejoin="round"/>
    </svg>'''

def barra(pct,color):
    pct=max(0,min(100,pct))
    return f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div>'

def tabla_trades(trades, bot_id):
    if not trades: return ""
    rows = ""
    for i, t in enumerate(reversed(trades[-20:])):
        num = len(trades) - i
        gan = t["ganancia"]
        gc = "#2ee6a0" if gan>=0 else "#ff5c6c"
        razon = t.get("razon","")
        if "Take" in razon or "TP" in razon: ci,cc="TP ✅","#2ee6a0"
        elif "Stop" in razon or "SL" in razon or "Guardrail" in razon: ci,cc="SL ❌","#ff5c6c"
        else: ci,cc="EOD 🕐","#7a8699"
        pos=t.get("posicion","")
        di="▲" if pos=="LONG" else ("▼" if pos=="SHORT" else "—")
        dc="#2ee6a0" if pos=="LONG" else ("#ff5c6c" if pos=="SHORT" else "#7a8699")
        fecha=t["fecha"][:10] if t.get("fecha") else "—"
        rows+=f'<tr><td style="color:#7a8699">{num}</td><td>{fecha}</td><td style="color:{dc}">{di} {pos}</td><td style="color:{cc}">{ci}</td><td style="color:{gc};text-align:right">${gan:+,.0f}</td></tr>'
    return f'''<div class="trades-toggle" onclick="tg('tr-{bot_id}')" id="btn-tr-{bot_id}">Ver operaciones ▾</div>
    <div class="trades-wrap" id="tr-{bot_id}" style="display:none">
      <table class="trades-tbl"><thead><tr><th>#</th><th>Fecha</th><th>Dir</th><th>Cierre</th><th style="text-align:right">P&L</th></tr></thead>
      <tbody>{rows}</tbody></table></div>'''

def card_bot(d, idx):
    m=d["met"]; color=d["color"]
    es_ref = d.get("info")=="referencia"
    # Posicion
    if d["activas"]:
        chips="".join(f'<span class="pos-chip">{a}</span>' for a in d["activas"])
        pos=f'<div class="pos-row"><span class="pos-label">● ABIERTA</span>{chips}</div>'
    else:
        pos='<div class="pos-row"><span class="pos-label">○ FLAT</span><span class="pos-none">Sin posicion</span></div>'
    wr_c="var(--green)" if m["wr"]>=META_WR else ("var(--amber)" if m["wr"]>=35 else "var(--red)")
    gan_c="var(--green)" if m["ganancia"]>=0 else "var(--red)"
    pf_c="var(--green)" if m["pf"]>1 else "var(--red)"
    # Racha
    if m["racha"]>0:
        rc = "var(--green)" if m["racha_tipo"]=="W" else "var(--red)"
        racha_html=f'<span class="racha" style="color:{rc}">{m["racha"]}{m["racha_tipo"]} seguidas</span>'
    else:
        racha_html='<span class="racha" style="color:var(--muted)">sin ops</span>'
    meta=d.get("meta_ops",50)
    prog=m["ops"]/meta*100
    ref_badge='<span class="ref-badge">REFERENCIA</span>' if es_ref else ''
    spark = sparkline(m["equity"], color)
    tbl = tabla_trades(d.get("trades",[]), f"{idx}")
    return f'''<div class="card" style="border-top:2px solid {color}">
      <div class="card-head">
        <div class="card-title"><h2>{d["nombre"]}</h2><span class="mercado">{d["mercado"]}</span></div>
        <div class="card-head-right">{ref_badge}<span class="ops-count">{m["ops"]}/{meta}</span></div>
      </div>
      {pos}
      <div class="spark-wrap">{spark}</div>
      <div class="metrics-grid">
        <div class="metric"><span class="metric-label">WIN RATE</span><span class="metric-val" style="color:{wr_c}">{m["wr"]:.0f}%</span><span class="metric-sub">{m["wins"]}W/{m["losses"]}L</span></div>
        <div class="metric"><span class="metric-label">P.FACTOR</span><span class="metric-val" style="color:{pf_c}">{m["pf"]:.2f}</span><span class="metric-sub">{racha_html}</span></div>
        <div class="metric"><span class="metric-label">P&L SIM</span><span class="metric-val" style="color:{gan_c}">${m["ganancia"]:+,.0f}</span><span class="metric-sub">simulado</span></div>
        <div class="metric"><span class="metric-label">PEOR DD</span><span class="metric-val">${m["max_dd"]:,.0f}</span><span class="metric-sub">lim ${APEX_DD:,}</span></div>
      </div>
      <div class="prog-mini"><div class="prog-mini-label"><span>Progreso a {meta} ops</span><span>{prog:.0f}%</span></div>{barra(prog,color)}</div>
      {tbl}
    </div>'''

def card_claude(memoria, patrones):
    decisiones = [m for m in memoria if not str(m.get("mi_razon","")).startswith("Error")]
    total_dec = len(decisiones)
    enters = [d for d in decisiones if d.get("mi_decision")=="ENTER"]
    skips  = [d for d in decisiones if d.get("mi_decision")=="SKIP"]
    # Ultimas decisiones
    ult_html=""
    for d in reversed(decisiones[-6:]):
        dec=d.get("mi_decision","?")
        conf=d.get("mi_confianza",0)
        conf_pct=conf*100 if conf<=1 else conf
        razon=d.get("mi_razon","")[:70]
        sym=d.get("symbol","?"); acc=d.get("accion","")
        ts=d.get("timestamp","")[:16]
        res=d.get("resultado")
        dec_c="var(--green)" if dec=="ENTER" else "var(--muted)"
        if res=="TP": res_html='<span style="color:var(--green)">→ TP ✅</span>'
        elif res=="SL": res_html='<span style="color:var(--red)">→ SL ❌</span>'
        elif res: res_html=f'<span style="color:var(--muted)">→ {res}</span>'
        else: res_html=''
        ult_html+=f'''<div class="claude-dec">
          <div class="claude-dec-top"><span class="dec-badge" style="color:{dec_c}">{dec}</span>
            <span class="dec-sym">{acc} {sym}</span><span class="dec-conf">{conf_pct:.0f}%</span>{res_html}</div>
          <div class="claude-dec-razon">{razon}</div>
          <div class="claude-dec-ts">{ts}</div></div>'''
    # Patrones
    pat_total = patrones.get("total",0)
    pat_wr = patrones.get("wr",0)
    pat_gan = patrones.get("ganancia_total",0)
    errores = patrones.get("errores_recientes",[])
    aciertos = patrones.get("aciertos_recientes",[])
    lecciones=""
    for e in errores[-3:]:
        lecciones+=f'<div class="leccion leccion-err">❌ {e.get("fecha","")}: {e.get("razon","")[:60]} → -${abs(e.get("perdida",0)):,.0f}</div>'
    for a in aciertos[-3:]:
        lecciones+=f'<div class="leccion leccion-ok">✅ {a.get("fecha","")}: {a.get("razon","")[:60]} → +${a.get("ganancia",0):,.0f}</div>'
    if not lecciones:
        lecciones='<div class="leccion" style="color:var(--muted)">Claude aun esta acumulando patrones...</div>'
    gan_c="var(--green)" if pat_gan>=0 else "var(--red)"
    return f'''<div class="claude-panel">
      <div class="claude-head">
        <div class="claude-title"><span class="claude-icon">🧠</span><h2>Claude Brain</h2></div>
        <span class="claude-status">● ACTIVO</span>
      </div>
      <div class="claude-stats">
        <div class="cstat"><span class="cstat-val">{total_dec}</span><span class="cstat-label">decisiones</span></div>
        <div class="cstat"><span class="cstat-val" style="color:var(--green)">{len(enters)}</span><span class="cstat-label">ENTER</span></div>
        <div class="cstat"><span class="cstat-val" style="color:var(--muted)">{len(skips)}</span><span class="cstat-label">SKIP</span></div>
        <div class="cstat"><span class="cstat-val" style="color:{gan_c}">${pat_gan:+,.0f}</span><span class="cstat-label">P&L decisiones</span></div>
      </div>
      <div class="claude-cols">
        <div class="claude-col">
          <h4>Ultimas decisiones</h4>
          <div class="claude-decs">{ult_html if ult_html else '<div class="leccion" style="color:var(--muted)">Sin decisiones aun</div>'}</div>
        </div>
        <div class="claude-col">
          <h4>Patrones aprendidos</h4>
          <div class="lecciones">{lecciones}</div>
        </div>
      </div>
    </div>'''

# ============================================================
#  PUBLICAR
# ============================================================
def push_html():
    if not TOKEN: print("Sin GH_TOKEN"); return
    with open("index.html","rb") as f: html=f.read()
    url=f"https://api.github.com/repos/{OWNER}/panel-trading/contents/index.html"
    req=urllib.request.Request(url); req.add_header("Authorization",f"Bearer {TOKEN}")
    req.add_header("Accept","application/vnd.github+json")
    try:
        with urllib.request.urlopen(req) as r: sha=json.load(r)["sha"]
    except: sha=None
    payload={"message":f"Dashboard {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             "content":base64.b64encode(html).decode(),"branch":"main"}
    if sha: payload["sha"]=sha
    req2=urllib.request.Request(url,data=json.dumps(payload).encode(),method="PUT")
    req2.add_header("Authorization",f"Bearer {TOKEN}")
    req2.add_header("Accept","application/vnd.github+json")
    req2.add_header("Content-Type","application/json")
    try:
        with urllib.request.urlopen(req2): print("Dashboard publicado en GitHub Pages")
    except Exception as e: print(f"Error push: {e}")

# ============================================================
#  MAIN
# ============================================================
print("Leyendo estados de los bots...")
datos=[]
for b in BOTS:
    estado=fetch_json(b["repo"], b["archivo"])
    trades=extraer_trades(estado, b["tipo"])
    met=calc_metricas(trades)
    activas=posicion_abierta(estado, b["tipo"])
    datos.append({**b,"met":met,"activas":activas,"estado":estado,"trades":trades})
    print(f"  {b['nombre']}: {met['ops']} ops, WR {met['wr']:.0f}%")

print("Leyendo Claude Brain...")
memoria, patrones = cargar_claude()
print(f"  {len(memoria)} entradas en memoria")

# Totales globales
cap_total = sum(d["estado"].get("capital",CAPITAL) if d["estado"] else CAPITAL for d in datos if d.get("info")!="referencia")
gan_total = sum(d["met"]["ganancia"] for d in datos if d.get("info")!="referencia")
ops_total = sum(d["met"]["ops"] for d in datos if d.get("info")!="referencia")
wins_total = sum(d["met"]["wins"] for d in datos if d.get("info")!="referencia")
wr_global = wins_total/ops_total*100 if ops_total>0 else 0
activas_total = sum(len(d["activas"]) for d in datos)

gg_c="var(--green)" if gan_total>=0 else "var(--red)"
wr_g_c="var(--green)" if wr_global>=META_WR else "var(--amber)"

cards="".join(card_bot(d,i) for i,d in enumerate(datos))
claude_html=card_claude(memoria, patrones)
ahora=datetime.now().strftime("%d %b %Y · %H:%M UTC")

html=f'''<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="120">
<title>Trading Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Sora:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#070a10;--panel:#10151f;--panel-2:#171e2b;--line:#212a3a;--text:#e4e9f0;--muted:#6b7689;--green:#2ee6a0;--amber:#ffb547;--red:#ff5c6c;--accent:#4d9fff;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--bg);color:var(--text);font-family:'Sora',sans-serif;padding:20px 14px 60px;background-image:radial-gradient(circle at 15% 0%,rgba(77,159,255,0.07),transparent 42%),radial-gradient(circle at 95% 8%,rgba(46,230,160,0.05),transparent 38%);min-height:100vh;}}
.wrap{{max-width:1160px;margin:0 auto;}}
.top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;flex-wrap:wrap;gap:10px;}}
.top h1{{font-size:22px;font-weight:800;letter-spacing:-0.5px;display:flex;align-items:center;gap:10px;}}
.top h1 .live{{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 10px var(--green);animation:pulse 2s infinite;}}
.top .ts{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--muted);}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.4}}}}
/* Header global */
.global{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:24px;}}
.gstat{{background:linear-gradient(135deg,var(--panel),var(--panel-2));border:1px solid var(--line);border-radius:13px;padding:16px 18px;}}
.gstat-label{{font-size:10px;letter-spacing:1px;color:var(--muted);text-transform:uppercase;}}
.gstat-val{{font-family:'IBM Plex Mono',monospace;font-size:25px;font-weight:600;margin-top:5px;}}
.gstat-sub{{font-size:11px;color:var(--muted);margin-top:2px;}}
@media (max-width:860px){{.global{{grid-template-columns:repeat(2,1fr);}} .top h1{{font-size:18px;}}}}
/* Claude panel */
.claude-panel{{background:linear-gradient(135deg,rgba(201,139,255,0.06),var(--panel));border:1px solid rgba(201,139,255,0.2);border-radius:16px;padding:22px;margin-bottom:24px;}}
.claude-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;}}
.claude-title{{display:flex;align-items:center;gap:10px;}}
.claude-title h2{{font-size:19px;font-weight:700;}}
.claude-icon{{font-size:22px;}}
.claude-status{{font-size:11px;font-weight:700;color:var(--green);letter-spacing:0.5px;}}
.claude-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px;}}
.cstat{{display:flex;flex-direction:column;gap:3px;}}
.cstat-val{{font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:600;}}
.cstat-label{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px;}}
.claude-cols{{display:grid;grid-template-columns:1fr 1fr;gap:20px;}}
.claude-col h4{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:12px;}}
.claude-dec{{background:var(--panel-2);border-radius:9px;padding:11px 13px;margin-bottom:9px;}}
.claude-dec-top{{display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:5px;flex-wrap:wrap;}}
.dec-badge{{font-weight:700;font-family:'IBM Plex Mono',monospace;font-size:12px;}}
.dec-sym{{color:var(--text);font-family:'IBM Plex Mono',monospace;font-size:12px;}}
.dec-conf{{color:var(--accent);font-family:'IBM Plex Mono',monospace;font-size:12px;margin-left:auto;}}
.claude-dec-razon{{font-size:12px;color:var(--muted);line-height:1.5;}}
.claude-dec-ts{{font-size:10px;color:var(--muted);font-family:'IBM Plex Mono',monospace;margin-top:4px;opacity:0.6;}}
.lecciones{{display:flex;flex-direction:column;gap:8px;}}
.leccion{{font-size:12px;line-height:1.5;padding:9px 12px;border-radius:8px;background:var(--panel-2);}}
.leccion-err{{border-left:2px solid var(--red);}}
.leccion-ok{{border-left:2px solid var(--green);}}
@media (max-width:760px){{.claude-cols{{grid-template-columns:1fr;}} .claude-stats{{grid-template-columns:repeat(2,1fr);}}}}
/* Grid de bots */
.section-label{{display:flex;align-items:center;gap:9px;font-size:12px;font-weight:700;letter-spacing:1.5px;color:var(--muted);margin:8px 0 16px;text-transform:uppercase;}}
.grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;}}
@media (max-width:980px){{.grid{{grid-template-columns:1fr 1fr;}}}}
@media (max-width:680px){{.grid{{grid-template-columns:1fr;}}}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;}}
.card-head{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:13px;}}
.card-title h2{{font-size:16px;font-weight:700;}}
.mercado{{font-size:11px;color:var(--muted);font-family:'IBM Plex Mono',monospace;}}
.card-head-right{{display:flex;align-items:center;gap:6px;}}
.ops-count{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--muted);background:var(--panel-2);padding:4px 9px;border-radius:20px;}}
.ref-badge{{font-size:8px;font-weight:700;color:var(--muted);background:var(--panel-2);padding:3px 6px;border-radius:4px;letter-spacing:0.5px;}}
.pos-row{{display:flex;align-items:center;gap:9px;margin-bottom:13px;padding-bottom:12px;border-bottom:1px solid var(--line);flex-wrap:wrap;}}
.pos-label{{font-size:10px;letter-spacing:0.5px;color:var(--muted);}}
.pos-chip{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--accent);background:rgba(77,159,255,0.1);padding:3px 9px;border-radius:6px;}}
.pos-none{{font-size:12px;color:var(--muted);}}
.spark-wrap{{margin-bottom:14px;height:48px;}}
.spark-wrap svg{{width:100%;height:48px;display:block;}}
.metrics-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;}}
.metric{{display:flex;flex-direction:column;gap:1px;}}
.metric-label{{font-size:9px;letter-spacing:0.6px;color:var(--muted);}}
.metric-val{{font-family:'IBM Plex Mono',monospace;font-size:20px;font-weight:600;}}
.metric-sub{{font-size:10px;color:var(--muted);}}
.racha{{font-size:10px;font-family:'IBM Plex Mono',monospace;}}
.prog-mini{{margin-bottom:6px;}}
.prog-mini-label{{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:5px;}}
.prog-mini-label span:last-child{{font-family:'IBM Plex Mono',monospace;}}
.bar-track{{height:6px;background:var(--panel-2);border-radius:6px;overflow:hidden;}}
.bar-fill{{height:100%;border-radius:6px;transition:width 0.6s;}}
.trades-toggle{{font-size:11px;color:var(--accent);cursor:pointer;margin-top:12px;user-select:none;font-weight:600;}}
.trades-wrap{{margin-top:10px;}}
.trades-tbl{{width:100%;border-collapse:collapse;font-size:11px;}}
.trades-tbl th{{text-align:left;color:var(--muted);font-weight:500;padding:5px 6px;border-bottom:1px solid var(--line);font-size:10px;letter-spacing:0.5px;}}
.trades-tbl td{{padding:5px 6px;border-bottom:1px solid rgba(33,42,58,0.5);font-family:'IBM Plex Mono',monospace;}}
.footer{{text-align:center;margin-top:30px;font-size:11px;color:var(--muted);font-family:'IBM Plex Mono',monospace;line-height:1.8;}}
.footer b{{color:var(--text);}}
</style></head><body><div class="wrap">
  <div class="top">
    <h1><span class="live"></span>Trading Dashboard</h1>
    <div class="ts">Auto-refresh 2min · {ahora}</div>
  </div>

  <div class="global">
    <div class="gstat"><div class="gstat-label">Capital Total</div><div class="gstat-val">${cap_total:,.0f}</div><div class="gstat-sub">5 estrategias</div></div>
    <div class="gstat"><div class="gstat-label">P&L Combinado</div><div class="gstat-val" style="color:{gg_c}">${gan_total:+,.0f}</div><div class="gstat-sub">simulado</div></div>
    <div class="gstat"><div class="gstat-label">WR Global</div><div class="gstat-val" style="color:{wr_g_c}">{wr_global:.0f}%</div><div class="gstat-sub">{wins_total}W de {ops_total}</div></div>
    <div class="gstat"><div class="gstat-label">Ops Totales</div><div class="gstat-val">{ops_total}</div><div class="gstat-sub">acumuladas</div></div>
    <div class="gstat"><div class="gstat-label">Posiciones</div><div class="gstat-val" style="color:{'var(--accent)' if activas_total else 'var(--muted)'}">{activas_total}</div><div class="gstat-sub">abiertas ahora</div></div>
  </div>

  {claude_html}

  <div class="section-label">◆ ESTRATEGIAS EN VALIDACION</div>
  <div class="grid">{cards}</div>

  <div class="footer">
    Meta: <b>WR ≥ {META_WR}%</b> sostenido por estrategia → luz verde para fondeo<br>
    Sistema autonomo en Railway · Claude Brain analiza cada señal · Datos en vivo
  </div>
</div><script>
function tg(id){{
  var w=document.getElementById(id), b=document.getElementById('btn-'+id);
  if(w.style.display==='none'){{w.style.display='block';b.innerHTML='Ocultar operaciones ▴';}}
  else{{w.style.display='none';b.innerHTML='Ver operaciones ▾';}}
}}
</script></body></html>'''

with open("index.html","w") as f:
    f.write(html)
print("\nindex.html generado correctamente")
push_html()
