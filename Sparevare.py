"""
Handlekurv Optimizer
Kjør med: streamlit run app.py

All Kassalapp-kommunikasjon skjer fra brukerens nettleser (JS fetch).
Python håndterer kun Supabase og app-logikk.
"""

import uuid
import json
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ══════════════════════════════════════════════════════════════════════════════
# KONFIGURASJON
# ══════════════════════════════════════════════════════════════════════════════

KASSALAPP_KEY = "XtpH4ZI1stdvqogYHzz5iyFoRKW89zGsTvMdtvvX"
SUPABASE_URL  = "https://liptedpuxhifwqkiglpn.supabase.co"
SUPABASE_KEY  = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6"
    "ImxpcHRlZHB1eGhpZndxa2lnbHBuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgxNjUxNzMs"
    "ImV4cCI6MjA5Mzc0MTE3M30.tRQgdqF0DAJRcrcNifRGgMo4gRwmVNdIiUdvBYETDgg"
)

# ══════════════════════════════════════════════════════════════════════════════
# BUTIKK-METADATA
# ══════════════════════════════════════════════════════════════════════════════

STORES = {
    "REMA_1000":  {"name": "REMA 1000",  "emoji": "🔴"},
    "KIWI":       {"name": "KIWI",       "emoji": "🟡"},
    "SPAR_NO":    {"name": "SPAR",       "emoji": "🟢"},
    "MENY_NO":    {"name": "Meny",       "emoji": "🔵"},
    "BUNNPRIS":   {"name": "Bunnpris",   "emoji": "🟠"},
    "COOP_EXTRA": {"name": "Coop Extra", "emoji": "🟣"},
    "COOP_OBS":   {"name": "Obs",        "emoji": "⚫"},
    "COOP_MEGA":  {"name": "Coop Mega",  "emoji": "🟤"},
    "COOP_PRIX":  {"name": "Coop Prix",  "emoji": "🔴"},
    "JOKER_NO":   {"name": "Joker",      "emoji": "🃏"},
    "ODA_NO":     {"name": "Oda",        "emoji": "📦"},
}

def sname(code): return STORES.get(code, {}).get("name", code)
def semoji(code): return STORES.get(code, {}).get("emoji", "🏪")

# ══════════════════════════════════════════════════════════════════════════════
# DATABASE (Supabase – Python-side for kurv-oppretting/sletting/oppdatering)
# ══════════════════════════════════════════════════════════════════════════════

class Database:
    def __init__(self):
        self._sb = None
        self._ok = False
        try:
            from supabase import create_client
            self._sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            self._sb.table("handlekurver").select("id").limit(1).execute()
            self._ok = True
        except Exception as e:
            print(f"[DB] {e}")

    @property
    def connected(self): return self._ok

    def _q(self, fn):
        try: return fn()
        except Exception as e: print(f"[DB] {e}"); return None

    def create_kurv(self, name: str) -> Optional[dict]:
        if not self._ok: return None
        row = {"id": str(uuid.uuid4()), "name": name,
               "created_at": datetime.utcnow().isoformat()}
        self._q(lambda: self._sb.table("handlekurver").insert(row).execute())
        row["items"] = []
        return row

    def get_kurver(self) -> list[dict]:
        if not self._ok: return []
        r1 = self._q(lambda: self._sb.table("handlekurver").select("*").order("created_at").execute())
        r2 = self._q(lambda: self._sb.table("handlekurv_items").select("*").order("added_at").execute())
        kurver = r1.data if r1 else []
        items  = r2.data if r2 else []
        for k in kurver:
            k["items"] = [i for i in items if i["kurv_id"] == k["id"]]
        return kurver

    def delete_kurv(self, kid: str):
        if not self._ok: return
        self._q(lambda: self._sb.table("handlekurv_items").delete().eq("kurv_id", kid).execute())
        self._q(lambda: self._sb.table("handlekurver").delete().eq("id", kid).execute())

    def set_qty(self, iid: str, qty: int):
        if not self._ok: return
        self._q(lambda: self._sb.table("handlekurv_items").update({"quantity": qty}).eq("id", iid).execute())

    def del_item(self, iid: str):
        if not self._ok: return
        self._q(lambda: self._sb.table("handlekurv_items").delete().eq("id", iid).execute())

# ══════════════════════════════════════════════════════════════════════════════
# HTML-KOMPONENTER (raw strings – ingen f-string konflikt med JS)
# Verdier injiseres med .replace() på markerte plassholdere
# ══════════════════════════════════════════════════════════════════════════════

SEARCH_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
* { box-sizing:border-box; margin:0; padding:0; }
body { background:transparent; font-family:'DM Sans',sans-serif; color:#fff; padding:2px; }
.wrap { display:flex; gap:8px; margin-bottom:10px; }
input { flex:1; background:#0f0f1a; border:1px solid #22223a; border-radius:10px; color:#fff; font-size:15px; padding:10px 14px; outline:none; transition:border-color 0.15s; }
input:focus { border-color:#6c63ff; box-shadow:0 0 0 3px rgba(108,99,255,0.15); }
input::placeholder { color:#444; }
button.sok { background:#6c63ff; color:#fff; border:none; border-radius:10px; font-weight:700; font-size:13px; padding:10px 18px; cursor:pointer; white-space:nowrap; }
button.sok:hover { background:#5a52e0; }
button.sok:disabled { background:#2a2a3a; color:#555; cursor:not-allowed; }
.status { color:#555; font-size:12px; margin:4px 0 10px; min-height:18px; }
.kurv-row { display:flex; align-items:center; gap:8px; margin-bottom:12px; }
.kurv-row label { color:#555; font-size:13px; white-space:nowrap; }
select { background:#0f0f1a; border:1px solid #22223a; border-radius:8px; color:#ccc; font-size:13px; padding:6px 10px; flex:1; }
.results { display:flex; flex-direction:column; gap:5px; }
.row { background:#0f0f1a; border:1px solid #1a1a2e; border-radius:10px; padding:10px 14px; display:flex; align-items:center; gap:10px; }
.row:hover { border-color:#2a2a3a; }
.info { flex:1; }
.name { font-weight:600; font-size:14px; color:#eee; }
.meta { font-size:11px; color:#555; margin-top:2px; }
.price { font-weight:700; font-size:15px; color:#fff; white-space:nowrap; }
button.add { background:#6c63ff; color:#fff; border:none; border-radius:8px; width:32px; height:32px; font-size:18px; cursor:pointer; flex-shrink:0; }
button.add:hover { background:#5a52e0; }
button.add.done { background:#1e4d33; color:#4ade80; font-size:14px; }
</style></head><body>
<div class="wrap">
  <input id="q" type="text" placeholder="Skriv produktnavn, f.eks.  melk  &#183;  havregryn ..."
         onkeydown="if(event.key==='Enter') doSearch()" />
  <button class="sok" id="sokBtn" onclick="doSearch()">S&#248;k &#8594;</button>
</div>
<div class="status" id="status"></div>
<div class="kurv-row" id="kurvRow" style="display:none">
  <label>Legg til i:</label>
  <select id="kurvSel"></select>
</div>
<div class="results" id="results"></div>
<script>
var API_KEY    = "%%KASSALAPP_KEY%%";
var SUPA_URL   = "%%SUPABASE_URL%%";
var SUPA_KEY   = "%%SUPABASE_KEY%%";
var kurver     = %%KURVER_JSON%%;
var allRes     = [];

var sel = document.getElementById("kurvSel");
kurver.forEach(function(k) {
  var o = document.createElement("option");
  o.value = k; o.textContent = "\uD83E\uDDFA " + k;
  sel.appendChild(o);
});
if (kurver.length > 0) document.getElementById("kurvRow").style.display = "flex";

function doSearch() {
  var q = document.getElementById("q").value.trim();
  if (!q) return;
  var btn    = document.getElementById("sokBtn");
  var status = document.getElementById("status");
  btn.disabled = true; btn.textContent = "S\u00f8ker...";
  status.textContent = ""; document.getElementById("results").innerHTML = "";
  var url = "https://kassal.app/api/v1/products?search=" + encodeURIComponent(q) + "&size=25&unique=true";
  fetch(url, { headers: { "Authorization": "Bearer " + API_KEY, "Accept": "application/json" } })
  .then(function(r) {
    if (!r.ok) { status.textContent = "Feil fra Kassalapp (" + r.status + ")"; throw new Error(r.status); }
    return r.json();
  })
  .then(function(data) {
    allRes = data.data || [];
    status.textContent = allRes.length > 0
      ? allRes.length + " resultater for \u00AB" + q + "\u00BB"
      : "Ingen resultater. Pr\u00f8v et annet s\u00f8keord.";
    render(allRes);
  })
  .catch(function() {})
  .finally(function() { btn.disabled = false; btn.textContent = "S\u00f8k \u2192"; });
}

function render(items) {
  var el = document.getElementById("results");
  el.innerHTML = "";
  items.forEach(function(p, i) {
    var name  = p.name  || "";
    var brand = p.brand || "";
    var ean   = p.ean   || "";
    var pris  = p.current_price;
    var store = (p.store && p.store.name) ? p.store.name : "";
    var meta  = [brand, store].filter(Boolean).join(" \u00b7 ");
    var priceStr = pris ? pris.toFixed(2) + " kr" : "\u2013";
    var row = document.createElement("div");
    row.className = "row";
    row.innerHTML =
      '<div class="info">' +
        '<div class="name">' + name + '</div>' +
        '<div class="meta">' + meta + (ean ? " \u00b7 EAN " + ean : "") + '</div>' +
      '</div>' +
      '<div class="price">' + priceStr + '</div>' +
      '<button class="add" id="ab' + i + '" onclick="addItem(' + i + ',this)">\uFF0B</button>';
    el.appendChild(row);
  });
}

function addItem(idx, btn) {
  var p = allRes[idx];
  var kurvNavn = document.getElementById("kurvSel").value;
  if (!kurvNavn) { alert("Velg en handlekurv f\u00f8rst."); return; }
  btn.disabled = true; btn.textContent = "...";
  fetch(SUPA_URL + "/rest/v1/handlekurver?name=eq." + encodeURIComponent(kurvNavn) + "&select=id", {
    headers: { "apikey": SUPA_KEY, "Authorization": "Bearer " + SUPA_KEY }
  })
  .then(function(r) { return r.json(); })
  .then(function(rows) {
    if (!rows || !rows.length) { alert("Fant ikke handlekurven."); throw new Error("not found"); }
    return fetch(SUPA_URL + "/rest/v1/handlekurv_items", {
      method: "POST",
      headers: {
        "apikey": SUPA_KEY, "Authorization": "Bearer " + SUPA_KEY,
        "Content-Type": "application/json", "Prefer": "return=minimal"
      },
      body: JSON.stringify({
        id: crypto.randomUUID(), kurv_id: rows[0].id,
        name: p.name || "", ean: p.ean || null, brand: p.brand || null,
        quantity: 1, added_at: new Date().toISOString()
      })
    });
  })
  .then(function() { btn.className = "add done"; btn.textContent = "\u2713"; })
  .catch(function(e) { if (e.message !== "not found") alert("Feil: " + e); btn.disabled = false; btn.textContent = "\uFF0B"; });
}
</script></body></html>"""

ANALYSE_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
* { box-sizing:border-box; margin:0; padding:0; }
body { background:transparent; font-family:'DM Sans',sans-serif; color:#fff; padding:2px; }
button.run { width:100%; background:#6c63ff; color:#fff; border:none; border-radius:10px; font-weight:700; font-size:14px; padding:12px; cursor:pointer; margin-bottom:10px; }
button.run:hover { background:#5a52e0; }
button.run:disabled { background:#2a2a3a; color:#555; cursor:not-allowed; }
.status { color:#555; font-size:12px; margin-bottom:10px; min-height:16px; }
h3 { font-size:12px; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:#555; margin:16px 0 8px; }
.srow { background:#0f0f1a; border:1px solid #1a1a2e; border-radius:10px; padding:10px 14px; margin-bottom:6px; display:flex; align-items:center; gap:10px; }
.srow.best { border-color:#6c63ff; background:linear-gradient(135deg,#0f0f1a,#16123a); }
.sname { flex:1; font-weight:600; font-size:14px; }
.ssub { font-size:11px; color:#555; }
.sprice { font-weight:700; font-size:15px; white-space:nowrap; }
.badge { background:#6c63ff; color:#fff; padding:2px 8px; border-radius:20px; font-size:11px; font-weight:700; }
.diff { color:#ef4444; font-size:13px; }
.savings { background:linear-gradient(135deg,#091a12,#0b1f14); border:1px solid #1e4d33; border-radius:12px; padding:14px 18px; margin:10px 0; }
.sav-num { font-size:2rem; font-weight:800; color:#4ade80; line-height:1; }
.sav-lbl { color:#555; font-size:12px; margin-top:4px; }
.cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:8px; margin-top:8px; }
.card { background:#0f0f1a; border:1px solid #1a1a2e; border-radius:10px; padding:12px; }
.cname { font-weight:700; font-size:13px; margin-bottom:4px; }
.cprice { font-size:1.3rem; font-weight:800; color:#6c63ff; margin-bottom:6px; }
.citem { font-size:11px; color:#666; margin-bottom:2px; }
</style></head><body>
<button class="run" id="btn" onclick="run()">&#128640; Analyser priser</button>
<div class="status" id="status"></div>
<div id="out"></div>
<script>
var API_KEY   = "%%KASSALAPP_KEY%%";
var items     = %%ITEMS_JSON%%;
var preferred = %%PREFERRED_JSON%%;
var stores    = %%STORES_JSON%%;
var kombiner  = %%KOMBINER%%;
var maks      = %%MAKS%%;

function sname(c) { return (stores[c] && stores[c].name) ? stores[c].name : c; }
function semoji(c) { return (stores[c] && stores[c].emoji) ? stores[c].emoji : "\uD83C\uDFEA"; }

function run() {
  var btn = document.getElementById("btn");
  var status = document.getElementById("status");
  var out = document.getElementById("out");
  btn.disabled = true; btn.textContent = "Henter priser...";
  status.textContent = ""; out.innerHTML = "";

  var eans = items.map(function(i) { return i.ean; }).filter(Boolean);
  if (!eans.length) { status.textContent = "Ingen EAN-koder funnet."; btn.disabled=false; btn.textContent="\uD83D\uDE80 Analyser priser"; return; }

  fetch("https://kassal.app/api/v1/products/prices-bulk", {
    method: "POST",
    headers: { "Authorization": "Bearer " + API_KEY, "Accept": "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ eans: eans, days: 7, aggregation: "min" })
  })
  .then(function(r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
  .then(function(data) {
    var bulk = data.data || [];
    if (!bulk.length) { status.textContent = "Ingen prisdata funnet."; return; }

    var prices = {};
    bulk.forEach(function(p) {
      prices[p.ean] = {};
      (p.stores || []).forEach(function(s) {
        if (s.store && s.current_price != null) prices[p.ean][s.store] = parseFloat(s.current_price);
      });
    });

    var allS = new Set();
    Object.values(prices).forEach(function(d) { Object.keys(d).forEach(function(s) { allS.add(s); }); });
    var prefS = new Set(preferred.filter(function(s) { return allS.has(s); }));
    var active = Array.from(prefS.size ? prefS : allS);

    var ranking = [];
    active.forEach(function(code) {
      var tot = 0, found = 0;
      items.forEach(function(item) {
        if (!item.ean) return;
        var p = (prices[item.ean] || {})[code];
        if (p != null) { tot += p * (item.quantity || 1); found++; }
      });
      if (found) ranking.push({ code:code, name:sname(code), emoji:semoji(code), total:Math.round(tot*100)/100, found:found });
    });
    ranking.sort(function(a,b) { return a.total - b.total; });

    var medals = ["\uD83E\uDD47","\uD83E\uDD48","\uD83E\uDD49","4.","5."];
    var html = "<h3>\uD83C\uDFEA Beste enkeltbutikk</h3>";
    ranking.slice(0,5).forEach(function(r,i) {
      html += '<div class="srow ' + (i===0?"best":"") + '">' +
        '<div><div class="sname">' + medals[i] + " " + r.emoji + " " + r.name + '</div>' +
        '<div class="ssub">' + r.found + "/" + eans.length + " varer funnet</div></div>" +
        '<div class="sprice">' + r.total.toFixed(2) + " kr</div>" +
        (i===0 ? '<span class="badge">\u2713 Billigst</span>' : '<span class="diff">+' + (r.total-ranking[0].total).toFixed(2) + " kr</span>") +
        "</div>";
    });

    if (kombiner && maks > 1 && ranking.length > 1) {
      var asgn = [];
      items.forEach(function(item) {
        if (!item.ean) return;
        var valid = {};
        active.forEach(function(c) { var p=(prices[item.ean]||{})[c]; if(p!=null) valid[c]=p; });
        var keys = Object.keys(valid).sort(function(a,b){return valid[a]-valid[b];});
        if (!keys.length) return;
        asgn.push({ name:item.name, qty:item.quantity||1, code:keys[0], price:Math.round(valid[keys[0]]*(item.quantity||1)*100)/100, valid:valid });
      });

      for (var it=0; it<20; it++) {
        var uniq = [];
        asgn.forEach(function(a) { if (uniq.indexOf(a.code)===-1) uniq.push(a.code); });
        if (uniq.length <= maks) break;
        var cnts = {};
        uniq.forEach(function(s) { cnts[s] = asgn.filter(function(a){return a.code===s;}).length; });
        uniq.sort(function(a,b){return cnts[a]-cnts[b];});
        var sm = uniq[0], rest = uniq.slice(1);
        asgn.forEach(function(a) {
          if (a.code !== sm) return;
          var cands = rest.filter(function(s){return a.valid[s]!=null;}).sort(function(x,y){return a.valid[x]-a.valid[y];});
          if (cands.length) { a.code=cands[0]; a.price=Math.round(a.valid[cands[0]]*a.qty*100)/100; }
        });
      }

      var totalOpt = asgn.reduce(function(s,a){return s+a.price;},0);
      var bespar = Math.round((ranking[0].total - totalOpt)*100)/100;

      html += "<h3>\uD83D\uDD00 Optimal fordeling (" + maks + " butikker)</h3>";
      if (bespar > 0.5) {
        html += '<div class="savings"><div style="color:#4ade80;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:4px">Du sparer</div>' +
          '<div class="sav-num">' + bespar.toFixed(2) + ' kr</div>' +
          '<div class="sav-lbl">mot \u00e5 handle alt p\u00e5 ' + ranking[0].name + '</div></div>';
      } else {
        html += '<p style="color:#555;font-size:13px;margin-bottom:8px">Minimal besparelse (' + bespar.toFixed(2) + ' kr). Enklest \u00e5 handle alt p\u00e5 ' + ranking[0].name + '.</p>';
      }

      var groups = {};
      asgn.forEach(function(a) { if (!groups[a.code]) groups[a.code]=[]; groups[a.code].push(a); });
      html += '<div class="cards">';
      Object.keys(groups).forEach(function(code) {
        var varer = groups[code];
        var sub = varer.reduce(function(s,v){return s+v.price;},0);
        html += '<div class="card"><div class="cname">' + semoji(code) + " " + sname(code) + '</div>' +
          '<div class="cprice">' + sub.toFixed(2) + ' kr</div>';
        varer.forEach(function(v) {
          html += '<div class="citem">\u00b7 ' + v.name + ' \u00d7 ' + v.qty + ' \u2014 ' + v.price.toFixed(2) + ' kr</div>';
        });
        html += '</div>';
      });
      html += '</div>';
    }

    out.innerHTML = html;
    status.textContent = "\u2713 Analyse fullf\u00f8rt";
  })
  .catch(function(e) { status.textContent = "Feil: " + e.message; })
  .finally(function() { btn.disabled=false; btn.textContent="\uD83D\uDE80 Analyser priser"; });
}
</script></body></html>"""


def make_search_html(kurv_names: list) -> str:
    return (SEARCH_HTML
            .replace("%%KASSALAPP_KEY%%", KASSALAPP_KEY)
            .replace("%%SUPABASE_URL%%", SUPABASE_URL)
            .replace("%%SUPABASE_KEY%%", SUPABASE_KEY)
            .replace("%%KURVER_JSON%%", json.dumps(kurv_names)))


def make_analyse_html(items: list, preferred: list, kombiner: bool, maks: int) -> str:
    return (ANALYSE_HTML
            .replace("%%KASSALAPP_KEY%%", KASSALAPP_KEY)
            .replace("%%ITEMS_JSON%%", json.dumps(items))
            .replace("%%PREFERRED_JSON%%", json.dumps(preferred))
            .replace("%%STORES_JSON%%", json.dumps(STORES))
            .replace("%%KOMBINER%%", "true" if kombiner else "false")
            .replace("%%MAKS%%", str(maks)))


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT APP
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Handlekurv", page_icon="🛒", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.8rem; max-width: 1100px; }
.stApp { background: #080810; }
[data-testid="stSidebar"] { background: #0d0d18; border-right: 1px solid #1a1a2e; }
[data-testid="stSidebar"] * { color: #ccc !important; }
.stTabs [data-baseweb="tab-list"] { background:transparent; gap:0; border-bottom:1px solid #1a1a2e; }
.stTabs [data-baseweb="tab"] { font-family:'Syne',sans-serif; font-size:0.78rem; font-weight:600; letter-spacing:0.08em; color:#444 !important; padding:0.7rem 1.4rem; background:transparent; border-bottom:2px solid transparent; }
.stTabs [aria-selected="true"] { color:#fff !important; border-bottom:2px solid #6c63ff; }
.stTextInput input { background:#0f0f1a !important; border:1px solid #22223a !important; border-radius:10px !important; color:#fff !important; font-size:1rem !important; }
.stTextInput input:focus { border-color:#6c63ff !important; box-shadow:0 0 0 3px rgba(108,99,255,0.15) !important; }
.stNumberInput input { background:#0f0f1a !important; border:1px solid #22223a !important; border-radius:8px !important; color:#fff !important; }
.stButton > button { font-family:'Syne',sans-serif !important; font-weight:700 !important; font-size:0.82rem !important; border-radius:10px !important; border:none !important; padding:0.55rem 1.1rem !important; background:#6c63ff !important; color:#fff !important; }
.stButton > button:hover { background:#5a52e0 !important; }
hr { border-color:#1a1a2e !important; }
p, label { color:#bbb; }
h1,h2,h3,h4 { color:#fff; font-family:'Syne',sans-serif; }
[data-baseweb="tag"] { background:#6c63ff !important; }
[data-baseweb="select"] > div { background:#0f0f1a !important; border-color:#22223a !important; border-radius:10px !important; }
[data-baseweb="select"] * { color:#ccc !important; }
details summary { background:#0f0f1a !important; border:1px solid #1a1a2e !important; border-radius:10px !important; color:#ccc !important; padding:0.7rem 1rem !important; }
details > div { background:#0a0a14 !important; border:1px solid #1a1a2e !important; border-top:none !important; border-radius:0 0 10px 10px !important; padding:1rem !important; }
</style>
""", unsafe_allow_html=True)

# Init
@st.cache_resource
def get_db(): return Database()
db = get_db()

for k, v in {
    "favoritter": ["REMA_1000", "KIWI", "SPAR_NO", "BUNNPRIS"],
    "analyse_kid": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# DB-feilmelding
if not db.connected:
    st.error("⚠️ Database ikke tilkoblet. Kjør SQL-skjemaet i Supabase SQL Editor.")
    with st.expander("Vis SQL"):
        st.code("""
CREATE TABLE IF NOT EXISTS handlekurver (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS handlekurv_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kurv_id UUID NOT NULL REFERENCES handlekurver(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    ean TEXT,
    brand TEXT,
    quantity INTEGER DEFAULT 1,
    added_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE handlekurver DISABLE ROW LEVEL SECURITY;
ALTER TABLE handlekurv_items DISABLE ROW LEVEL SECURITY;
        """, language="sql")

# Sidebar
with st.sidebar:
    st.markdown("### 🏪 Mine butikker")
    st.caption("Velg butikkene du har i nærheten")
    st.session_state.favoritter = st.multiselect(
        "butikker", options=list(STORES.keys()),
        default=st.session_state.favoritter,
        format_func=lambda x: f"{STORES[x]['emoji']} {STORES[x]['name']}",
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("📡 Priser fra Kassalapp · Oppdateres daglig")

# Header
st.markdown("""
<p style="font-family:Syne;font-size:2.6rem;font-weight:800;color:#fff;letter-spacing:-0.02em;margin:0;line-height:1">🛒 Handlekurv Optimizer</p>
<p style="color:#555;font-size:0.95rem;margin:0.3rem 0 2rem;font-weight:300">Finn billigste butikk — eller kombiner flere og spar mer</p>
""", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["SØK ETTER VARER", "MINE HANDLEKURVER", "PRISANALYSE"])

# ── TAB 1: SØK ─────────────────────────────────────────────────────────────────
with tab1:
    kurver   = db.get_kurver()
    kurv_map = {k["name"]: k["id"] for k in kurver}
    components.html(make_search_html(list(kurv_map.keys())), height=700, scrolling=True)

# ── TAB 2: HANDLEKURVER ────────────────────────────────────────────────────────
with tab2:
    c1, c2 = st.columns([4, 1])
    with c1:
        ny = st.text_input("ny", placeholder="Navn på ny handlekurv, f.eks.  Ukeshandel ...",
                           label_visibility="collapsed", key="ny_kurv")
    with c2:
        if st.button("Opprett →", use_container_width=True):
            if ny.strip():
                db.create_kurv(ny.strip())
                st.rerun()
            else:
                st.warning("Skriv inn et navn.")

    kurver = db.get_kurver()

    if not kurver:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0">
          <p style="font-size:3rem;margin:0">🧺</p>
          <p style="color:#555;margin:0.5rem 0">Ingen handlekurver ennå</p>
          <p style="color:#333;font-size:0.85rem">Opprett en ovenfor</p>
        </div>""", unsafe_allow_html=True)
    else:
        for kurv in kurver:
            items  = kurv.get("items", [])
            antall = len(items)
            with st.expander(f"🧺  {kurv['name']}  ·  {antall} {'vare' if antall == 1 else 'varer'}", expanded=True):
                if not items:
                    st.markdown("<p style='color:#333;font-size:0.88rem'>Ingen varer. Søk i Søk-fanen og trykk ＋.</p>", unsafe_allow_html=True)
                for item in items:
                    c1, c2, c3 = st.columns([4, 1.2, 0.7])
                    with c1:
                        st.markdown(f"**{item['name']}**")
                        if item.get("brand"):
                            st.markdown(f"<span style='background:#1a1a2e;border-radius:5px;padding:1px 6px;font-size:11px;color:#666'>{item['brand']}</span>", unsafe_allow_html=True)
                        if item.get("ean"):
                            st.markdown(f"<span style='color:#333;font-size:11px'>EAN {item['ean']}</span>", unsafe_allow_html=True)
                    with c2:
                        ny_ant = st.number_input("ant", min_value=1, max_value=99,
                                                  value=int(item.get("quantity", 1)),
                                                  key=f"qty_{item['id']}", label_visibility="collapsed")
                        if ny_ant != item.get("quantity", 1):
                            db.set_qty(item["id"], ny_ant)
                    with c3:
                        if st.button("✕", key=f"del_{item['id']}"):
                            db.del_item(item["id"])
                            st.rerun()

                st.markdown("<br>", unsafe_allow_html=True)
                ca, cb = st.columns(2)
                with ca:
                    if st.button("📊  Analyser priser", key=f"an_{kurv['id']}", use_container_width=True):
                        st.session_state["analyse_kid"] = kurv["id"]
                        st.toast("Åpne Prisanalyse-fanen →")
                with cb:
                    if st.button("Slett kurv", key=f"dk_{kurv['id']}", use_container_width=True):
                        db.delete_kurv(kurv["id"])
                        st.rerun()

# ── TAB 3: PRISANALYSE ─────────────────────────────────────────────────────────
with tab3:
    kurver = db.get_kurver()
    if not kurver:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0">
          <p style="font-size:3rem;margin:0">📊</p>
          <p style="color:#555;margin:0.5rem 0">Ingen handlekurver å analysere</p>
          <p style="color:#333;font-size:0.85rem">Opprett en handlekurv og legg til varer først</p>
        </div>""", unsafe_allow_html=True)
    else:
        default_idx = 0
        if st.session_state.get("analyse_kid"):
            ids = [k["id"] for k in kurver]
            if st.session_state["analyse_kid"] in ids:
                default_idx = ids.index(st.session_state["analyse_kid"])

        valgt = st.selectbox("Handlekurv", options=kurver, index=default_idx,
                              format_func=lambda k: f"🧺  {k['name']}  ({len(k.get('items',[]))} varer)")

        c1, c2 = st.columns([2, 2])
        with c1:
            kombiner = st.toggle("Kombiner flere butikker", value=True)
        with c2:
            maks = st.select_slider("Maks butikker", options=[2,3,4,5], value=3,
                                     disabled=not kombiner) if kombiner else 1

        items = valgt.get("items", [])
        eans  = [i["ean"] for i in items if i.get("ean")]

        if not items:
            st.warning("Handlekurven er tom.")
        elif not eans:
            st.warning("Ingen varer med EAN-koder. Bruk søket i Søk-fanen.")
        elif not st.session_state.favoritter:
            st.warning("Velg minst én butikk i sidepanelet.")
        else:
            components.html(
                make_analyse_html(items, st.session_state.favoritter, kombiner, maks),
                height=900, scrolling=True
            )
