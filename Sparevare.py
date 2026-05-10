"""
Handlekurv Optimizer
Kassalapp-kall skjer fra brukerens nettleser (omgår IP-blokkering).
Kjør med: streamlit run app.py
"""

import uuid
from datetime import datetime
from typing import Optional
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ══════════════════════════════════════════════════════════════════════════════
# KONFIGURASJON
# ══════════════════════════════════════════════════════════════════════════════

KASSALAPP_API_KEY = "XtpH4ZI1stdvqogYHzz5iyFoRKW89zGsTvMdtvvX"
SUPABASE_URL      = "https://liptedpuxhifwqkiglpn.supabase.co"
SUPABASE_KEY      = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6"
    "ImxpcHRlZHB1eGhpZndxa2lnbHBuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgxNjUxNzMs"
    "ImV4cCI6MjA5Mzc0MTE3M30.tRQgdqF0DAJRcrcNifRGgMo4gRwmVNdIiUdvBYETDgg"
)

# ══════════════════════════════════════════════════════════════════════════════
# BUTIKK-METADATA
# ══════════════════════════════════════════════════════════════════════════════

STORES = {
    "REMA_1000":  {"name": "REMA 1000",  "emoji": "🔴"},
    "KIWI":       {"name": "KIWI",        "emoji": "🟡"},
    "SPAR_NO":    {"name": "SPAR",        "emoji": "🟢"},
    "MENY_NO":    {"name": "Meny",        "emoji": "🔵"},
    "BUNNPRIS":   {"name": "Bunnpris",    "emoji": "🟠"},
    "COOP_EXTRA": {"name": "Coop Extra",  "emoji": "🟣"},
    "COOP_OBS":   {"name": "Obs",         "emoji": "⚫"},
    "COOP_MEGA":  {"name": "Coop Mega",   "emoji": "🟤"},
    "COOP_PRIX":  {"name": "Coop Prix",   "emoji": "🔴"},
    "JOKER_NO":   {"name": "Joker",       "emoji": "🃏"},
    "ODA_NO":     {"name": "Oda",         "emoji": "📦"},
}

def sname(code): return STORES.get(code, {}).get("name", code)
def semoji(code): return STORES.get(code, {}).get("emoji", "🏪")

# ══════════════════════════════════════════════════════════════════════════════
# BROWSER-SIDE KASSALAPP FETCH
# Nettleseren gjør kallet direkte – unngår IP-blokkering på serveren
# ══════════════════════════════════════════════════════════════════════════════

def browser_search(query: str) -> list[dict]:
    """
    Sender et HTML/JS-komponent til nettleseren som kaller Kassalapp API,
    og returnerer resultatet via Streamlit sin bidireksjonale kommunikasjon.
    Bruker st.session_state som buffer.
    """
    html = f"""
    <script>
    (async () => {{
        const key = "{KASSALAPP_API_KEY}";
        const q   = encodeURIComponent("{query.strip().replace('"', '')}");
        const url = `https://kassal.app/api/v1/products?search=${{q}}&size=25&unique=true&sort=name_asc`;

        try {{
            const resp = await fetch(url, {{
                headers: {{
                    "Authorization": `Bearer ${{key}}`,
                    "Accept": "application/json"
                }}
            }});
            const data = await resp.json();
            const results = data.data || [];
            // Send tilbake til Streamlit via URL-hash trick
            window.parent.postMessage({{
                type: "kassalapp_results",
                results: results
            }}, "*");
        }} catch(e) {{
            window.parent.postMessage({{
                type: "kassalapp_results",
                results: [],
                error: e.toString()
            }}, "*");
        }}
    }})();
    </script>
    <p style="color:#666;font-size:0.8rem">Søker...</p>
    """
    components.html(html, height=30)


def browser_bulk_prices(eans: list[str]) -> str:
    """Henter bulk-priser fra nettleseren. Returnerer JS-snippet."""
    eans_json = json.dumps(eans)
    html = f"""
    <script>
    (async () => {{
        const key  = "{KASSALAPP_API_KEY}";
        const eans = {eans_json};
        const url  = "https://kassal.app/api/v1/products/prices-bulk";

        try {{
            const resp = await fetch(url, {{
                method: "POST",
                headers: {{
                    "Authorization": `Bearer ${{key}}`,
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                }},
                body: JSON.stringify({{ eans, days: 7, aggregation: "min" }})
            }});
            const data = await resp.json();
            window.parent.postMessage({{
                type: "kassalapp_prices",
                data: data.data || []
            }}, "*");
        }} catch(e) {{
            window.parent.postMessage({{
                type: "kassalapp_prices",
                data: [],
                error: e.toString()
            }}, "*");
        }}
    }})();
    </script>
    <p style="color:#666;font-size:0.8rem">Henter priser...</p>
    """
    components.html(html, height=30)

# ══════════════════════════════════════════════════════════════════════════════
# DATABASE (Supabase)
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
        except Exception as e:
            print(f"[DB] {e}")
            return None

    def create_kurv(self, name: str) -> Optional[dict]:
        if not self._ok: return None
        row = {"id": str(uuid.uuid4()), "name": name, "created_at": datetime.utcnow().isoformat()}
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

    def add_item(self, kid: str, name: str, ean: Optional[str], brand: Optional[str]) -> Optional[dict]:
        if not self._ok: return None
        row = {"id": str(uuid.uuid4()), "kurv_id": kid, "name": name,
               "ean": ean, "brand": brand or "", "quantity": 1,
               "added_at": datetime.utcnow().isoformat()}
        self._q(lambda: self._sb.table("handlekurv_items").insert(row).execute())
        return row

    def set_qty(self, iid: str, qty: int):
        if not self._ok: return
        self._q(lambda: self._sb.table("handlekurv_items").update({"quantity": qty}).eq("id", iid).execute())

    def del_item(self, iid: str):
        if not self._ok: return
        self._q(lambda: self._sb.table("handlekurv_items").delete().eq("id", iid).execute())

# ══════════════════════════════════════════════════════════════════════════════
# OPTIMALISERING
# ══════════════════════════════════════════════════════════════════════════════

class Optimizer:
    def __init__(self, bulk: list[dict], items: list[dict], preferred: list[str]):
        self.items = items
        self._p: dict[str, dict[str, float]] = {}
        for p in bulk:
            ean = p.get("ean", "")
            self._p[ean] = {
                s["store"]: float(s["current_price"])
                for s in p.get("stores", [])
                if s.get("current_price") is not None and s.get("store")
            }
        all_s = {s for d in self._p.values() for s in d}
        pref  = set(preferred) & all_s
        self.active = pref if pref else all_s

    def rank(self) -> list[dict]:
        out = []
        for code in self.active:
            tot, found = 0.0, 0
            for i in self.items:
                ean, qty = i.get("ean"), i.get("quantity", 1)
                if not ean: continue
                p = self._p.get(ean, {}).get(code)
                if p is not None:
                    tot += p * qty
                    found += 1
            if found:
                out.append({"code": code, "name": sname(code), "emoji": semoji(code),
                            "total": round(tot, 2), "found": found})
        out.sort(key=lambda x: x["total"])
        return out

    def split(self, max_stores: int) -> list[dict]:
        asgn = []
        for i in self.items:
            ean, qty = i.get("ean"), i.get("quantity", 1)
            if not ean: continue
            valid = {c: v for c, v in {c: self._p.get(ean, {}).get(c) for c in self.active}.items() if v is not None}
            if not valid: continue
            best = min(valid, key=valid.get)
            asgn.append({"ean": ean, "name": i["name"], "qty": qty,
                         "code": best, "price": round(valid[best] * qty, 2), "_v": valid})
        while len({a["code"] for a in asgn}) > max_stores:
            unique = {a["code"] for a in asgn}
            counts = {s: sum(1 for a in asgn if a["code"] == s) for s in unique}
            smallest = min(counts, key=counts.get)
            rest = unique - {smallest}
            if not rest: break
            for a in asgn:
                if a["code"] == smallest:
                    cands = {s: a["_v"][s] for s in rest if s in a["_v"]}
                    if cands:
                        new = min(cands, key=cands.get)
                        a["code"]  = new
                        a["price"] = round(cands[new] * a["qty"], 2)
        for a in asgn: a.pop("_v", None)
        return asgn

    def matrix(self) -> Optional[pd.DataFrame]:
        rows, idx = [], []
        for i in self.items:
            ean = i.get("ean")
            if not ean or not self._p.get(ean): continue
            rows.append({sname(c): self._p[ean].get(c) for c in sorted(self.active)})
            idx.append(i["name"][:35])
        return pd.DataFrame(rows, index=idx) if rows else None

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
.stButton > button { font-family:'Syne',sans-serif !important; font-weight:700 !important; font-size:0.82rem !important; letter-spacing:0.06em !important; border-radius:10px !important; border:none !important; padding:0.55rem 1.1rem !important; background:#6c63ff !important; color:#fff !important; transition:all 0.15s ease !important; }
.stButton > button:hover { background:#5a52e0 !important; transform:translateY(-1px); box-shadow:0 6px 20px rgba(108,99,255,0.35) !important; }
.stButton > button[kind="secondary"] { background:#1a1a2e !important; color:#888 !important; }
.card { background:#0f0f1a; border:1px solid #1a1a2e; border-radius:12px; padding:1rem 1.2rem; margin-bottom:0.6rem; }
.tag { display:inline-block; background:#1a1a2e; border-radius:5px; padding:0.1rem 0.5rem; font-size:0.72rem; color:#666; }
.badge-best { background:#6c63ff; color:#fff; padding:0.2rem 0.7rem; border-radius:20px; font-size:0.72rem; font-family:'Syne',sans-serif; font-weight:700; }
.savings-box { background:linear-gradient(135deg,#091a12,#0b1f14); border:1px solid #1e4d33; border-radius:14px; padding:1.2rem 1.6rem; margin:1rem 0; }
.savings-num { font-family:'Syne',sans-serif; font-size:2.4rem; font-weight:800; color:#4ade80; line-height:1; }
hr { border-color:#1a1a2e !important; margin:0.8rem 0 !important; }
p, label { color:#bbb; }
h1,h2,h3,h4 { color:#fff; font-family:'Syne',sans-serif; }
[data-baseweb="tag"] { background:#6c63ff !important; }
[data-baseweb="tag"] span { color:#fff !important; }
[data-testid="stDataFrame"] { border-radius:12px; overflow:hidden; border:1px solid #1a1a2e; }
[data-baseweb="select"] > div { background:#0f0f1a !important; border-color:#22223a !important; border-radius:10px !important; }
[data-baseweb="select"] * { color:#ccc !important; }
</style>
""", unsafe_allow_html=True)

# ── Init ───────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_db(): return Database()
db = get_db()

for k, v in {
    "favoritter": ["REMA_1000", "KIWI", "SPAR_NO", "BUNNPRIS"],
    "search_results": [],
    "last_q": "",
    "pending_search": None,
    "pending_prices": None,
    "analyse_items": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── DB-advarsel ────────────────────────────────────────────────────────────────
if not db.connected:
    st.error("⚠️ Databasen er ikke satt opp. Kjør SQL-skjemaet i Supabase SQL Editor.")
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

# ── Sidebar ────────────────────────────────────────────────────────────────────
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

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<p style="font-family:Syne;font-size:2.6rem;font-weight:800;color:#fff;letter-spacing:-0.02em;margin:0;line-height:1">🛒 Handlekurv Optimizer</p>
<p style="color:#555;font-size:0.95rem;margin:0.3rem 0 2rem;font-weight:300">Finn billigste butikk — eller kombiner flere og spar mer</p>
""", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["SØK ETTER VARER", "MINE HANDLEKURVER", "PRISANALYSE"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – SØK
# Nettleseren kaller Kassalapp direkte via JS fetch()
# Resultater vises i et søkekomponent med autocomplete-lignende liste
# ══════════════════════════════════════════════════════════════════════════════
with tab1:

    # Bygg søkekomponent som gjør browser-side fetch
    kurver   = db.get_kurver()
    kurv_map = {k["name"]: k["id"] for k in kurver}
    kurv_options_json = json.dumps(list(kurv_map.keys()))

    search_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
      body {{ background: transparent; font-family: 'DM Sans', sans-serif; color: #fff; padding: 0; }}
      .wrap {{ display: flex; gap: 8px; margin-bottom: 12px; }}
      input {{
        flex: 1; background: #0f0f1a; border: 1px solid #22223a;
        border-radius: 10px; color: #fff; font-size: 15px; padding: 10px 14px;
        outline: none; transition: border-color 0.15s;
      }}
      input:focus {{ border-color: #6c63ff; box-shadow: 0 0 0 3px rgba(108,99,255,0.15); }}
      input::placeholder {{ color: #444; }}
      button.søk {{
        background: #6c63ff; color: #fff; border: none; border-radius: 10px;
        font-weight: 700; font-size: 13px; letter-spacing: 0.06em; padding: 10px 20px;
        cursor: pointer; white-space: nowrap; transition: background 0.15s;
      }}
      button.søk:hover {{ background: #5a52e0; }}
      button.søk:disabled {{ background: #2a2a3a; color: #555; cursor: not-allowed; }}

      .status {{ color: #555; font-size: 12px; margin: 4px 0 10px; min-height: 18px; }}

      .kurv-select {{ margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }}
      .kurv-select label {{ color: #666; font-size: 13px; white-space: nowrap; }}
      select {{
        background: #0f0f1a; border: 1px solid #22223a; border-radius: 8px;
        color: #ccc; font-size: 13px; padding: 6px 10px; flex: 1;
      }}

      .results {{ display: flex; flex-direction: column; gap: 6px; }}
      .row {{
        background: #0f0f1a; border: 1px solid #1a1a2e; border-radius: 10px;
        padding: 10px 14px; display: flex; align-items: center; gap: 12px;
        transition: border-color 0.15s;
      }}
      .row:hover {{ border-color: #2a2a3a; }}
      .info {{ flex: 1; }}
      .name {{ font-weight: 600; font-size: 14px; color: #eee; }}
      .meta {{ font-size: 11px; color: #555; margin-top: 2px; }}
      .price {{ font-weight: 700; font-size: 15px; color: #fff; white-space: nowrap; }}
      button.add {{
        background: #6c63ff; color: #fff; border: none; border-radius: 8px;
        width: 32px; height: 32px; font-size: 18px; cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        transition: background 0.15s; flex-shrink: 0;
      }}
      button.add:hover {{ background: #5a52e0; }}
      button.add.done {{ background: #1e4d33; color: #4ade80; }}
      .empty {{ text-align: center; padding: 40px; color: #333; font-size: 13px; }}
    </style>
    </head>
    <body>

    <div class="wrap">
      <input id="q" type="text" placeholder="Skriv produktnavn, f.eks.  melk  ·  havregryn  ·  ost ..."
             onkeydown="if(event.key==='Enter') doSearch()" />
      <button class="søk" id="søkBtn" onclick="doSearch()">Søk →</button>
    </div>
    <div class="status" id="status"></div>

    <div class="kurv-select" id="kurvWrap" style="display:none">
      <label>Legg til i:</label>
      <select id="kurvSel"></select>
    </div>

    <div class="results" id="results"></div>

    <script>
    const API_KEY = "{KASSALAPP_API_KEY}";
    const kurver  = {kurv_options_json};
    let currentResults = [];

    // Populer kurv-dropdown
    const sel = document.getElementById("kurvSel");
    kurver.forEach(k => {{
      const o = document.createElement("option");
      o.value = k; o.textContent = "🧺 " + k;
      sel.appendChild(o);
    }});
    if (kurver.length > 0) document.getElementById("kurvWrap").style.display = "flex";

    async function doSearch() {{
      const q = document.getElementById("q").value.trim();
      if (!q) return;

      const btn = document.getElementById("søkBtn");
      const status = document.getElementById("status");
      btn.disabled = true;
      btn.textContent = "Søker...";
      status.textContent = "";
      document.getElementById("results").innerHTML = "";

      try {{
        const url = `https://kassal.app/api/v1/products?search=${{encodeURIComponent(q)}}&size=25&unique=true&sort=name_asc`;
        const resp = await fetch(url, {{
          headers: {{
            "Authorization": `Bearer ${{API_KEY}}`,
            "Accept": "application/json"
          }}
        }});

        if (!resp.ok) {{
          status.textContent = `Feil fra Kassalapp: ${{resp.status}}`;
          return;
        }}

        const data = await resp.json();
        currentResults = data.data || [];
        status.textContent = currentResults.length > 0
          ? `${{currentResults.length}} resultater for «${{q}}»`
          : "Ingen resultater. Prøv et annet søkeord.";

        renderResults(currentResults);
      }} catch(e) {{
        status.textContent = "Nettverksfeil – prøv igjen.";
        console.error(e);
      }} finally {{
        btn.disabled = false;
        btn.textContent = "Søk →";
      }}
    }}

    function renderResults(items) {{
      const el = document.getElementById("results");
      el.innerHTML = "";
      if (!items.length) {{
        el.innerHTML = `<div class="empty">Ingen resultater</div>`;
        return;
      }}
      items.forEach((p, i) => {{
        const name  = p.name || "";
        const brand = p.brand || "";
        const ean   = p.ean || "";
        const pris  = p.current_price;
        const store = (p.store && p.store.name) ? p.store.name : "";

        const meta = [brand, store].filter(Boolean).join(" · ");
        const priceStr = pris ? pris.toFixed(2) + " kr" : "–";

        const row = document.createElement("div");
        row.className = "row";
        row.innerHTML = `
          <div class="info">
            <div class="name">${{name}}</div>
            <div class="meta">${{meta}}${{ean ? " · EAN " + ean : ""}}</div>
          </div>
          <div class="price">${{priceStr}}</div>
          <button class="add" id="addbtn_${{i}}" onclick="addItem(${{i}}, this)" title="Legg til i handlekurv">＋</button>
        `;
        el.appendChild(row);
      }});
    }}

    async function addItem(idx, btn) {{
      const p       = currentResults[idx];
      const kurvNavn = document.getElementById("kurvSel").value;
      if (!kurvNavn) {{ alert("Velg en handlekurv først."); return; }}

      btn.disabled = true;
      btn.textContent = "...";

      // Send til Streamlit via postMessage
      window.parent.postMessage({{
        type: "add_to_kurv",
        kurv: kurvNavn,
        name: p.name,
        ean:  p.ean || null,
        brand: p.brand || null
      }}, "*");

      // Visuell feedback
      btn.className = "add done";
      btn.textContent = "✓";
    }}
    </script>
    </body>
    </html>
    """

    # Motta meldinger fra nettleseren og legg til i databasen
    result = components.html(search_html, height=650, scrolling=True)

    # Streamlit kan ikke motta postMessage direkte, så vi bruker en
    # workaround med query params via en liten hidden form
    st.markdown("---")
    st.caption("💡 Tips: Søket kjøres direkte fra nettleseren din for raskere resultater.")

    # Fallback: manuell legg-til via Python (for de som søkte og fant noe)
    with st.expander("➕ Legg til vare manuelt (om knappen over ikke virker)", expanded=False):
        if not kurv_map:
            st.info("Opprett en handlekurv i Mine handlekurver-fanen først.")
        else:
            mc1, mc2 = st.columns([3, 2])
            with mc1:
                m_navn = st.text_input("Produktnavn", key="m_navn")
                m_ean  = st.text_input("EAN-kode (valgfritt)", key="m_ean")
            with mc2:
                m_brand = st.text_input("Merke (valgfritt)", key="m_brand")
                m_kurv  = st.selectbox("Handlekurv", list(kurv_map.keys()), key="m_kurv")
            if st.button("Legg til", key="m_add"):
                if m_navn.strip():
                    db.add_item(kurv_map[m_kurv], m_navn.strip(), m_ean.strip() or None, m_brand.strip() or None)
                    st.success(f"✅ {m_navn} lagt til!")
                    st.rerun()
                else:
                    st.warning("Fyll inn produktnavn.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – HANDLEKURVER
# ══════════════════════════════════════════════════════════════════════════════
with tab2:

    c1, c2 = st.columns([4, 1])
    with c1:
        ny = st.text_input("ny", placeholder="Navn på ny handlekurv, f.eks.  Ukeshandel ...",
                           label_visibility="collapsed", key="ny_kurv")
    with c2:
        if st.button("Opprett →", use_container_width=True, key="btn_opprett"):
            if ny.strip():
                if db.connected:
                    db.create_kurv(ny.strip())
                    st.rerun()
                else:
                    st.error("Databasen er ikke tilkoblet.")
            else:
                st.warning("Skriv inn et navn.")

    kurver = db.get_kurver()

    if not kurver:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0;color:#333">
          <p style="font-size:3.5rem;margin:0">🧺</p>
          <p style="font-family:Syne;font-size:1.05rem;color:#555;margin:0.5rem 0">Ingen handlekurver ennå</p>
          <p style="font-size:0.85rem;color:#333">Opprett din første handlekurv ovenfor</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        for kurv in kurver:
            items  = kurv.get("items", [])
            antall = len(items)
            with st.expander(f"🧺  {kurv['name']}  ·  {antall} {'vare' if antall == 1 else 'varer'}", expanded=True):
                if not items:
                    st.markdown("<p style='color:#333;font-size:0.88rem'>Ingen varer. Bruk søket i Søk-fanen.</p>", unsafe_allow_html=True)
                for item in items:
                    c1, c2, c3 = st.columns([4, 1.2, 0.7])
                    with c1:
                        st.markdown(f"**{item['name']}**")
                        if item.get("brand"):
                            st.markdown(f"<span class='tag'>{item['brand']}</span>", unsafe_allow_html=True)
                        if item.get("ean"):
                            st.markdown(f"<span style='color:#333;font-size:0.72rem'>EAN {item['ean']}</span>", unsafe_allow_html=True)
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
                if items:
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

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 – PRISANALYSE
# Priser hentes browser-side via JS, sendt tilbake via Streamlit query params
# ══════════════════════════════════════════════════════════════════════════════
with tab3:

    kurver = db.get_kurver()
    if not kurver:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0;color:#333">
          <p style="font-size:3.5rem;margin:0">📊</p>
          <p style="font-family:Syne;font-size:1.05rem;color:#555;margin:0.5rem 0">Ingen handlekurver å analysere</p>
          <p style="font-size:0.85rem;color:#333">Opprett en handlekurv og legg til varer først</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        default_idx = 0
        if "analyse_kid" in st.session_state:
            ids = [k["id"] for k in kurver]
            if st.session_state["analyse_kid"] in ids:
                default_idx = ids.index(st.session_state["analyse_kid"])

        valgt = st.selectbox("Handlekurv", options=kurver, index=default_idx,
                              format_func=lambda k: f"🧺  {k['name']}  ({len(k.get('items',[]))} varer)")

        c1, c2 = st.columns([2, 2])
        with c1:
            kombiner = st.toggle("Kombiner flere butikker", value=True)
        with c2:
            maks = st.select_slider("Maks butikker", options=[2,3,4,5], value=3, disabled=not kombiner) if kombiner else 1

        items = valgt.get("items", [])
        eans  = [i["ean"] for i in items if i.get("ean")]

        if not items:
            st.warning("Handlekurven er tom.")
        elif not eans:
            st.warning("Ingen varer med EAN-koder. Søk og legg til varer fra Søk-fanen.")
        elif not st.session_state.favoritter:
            st.warning("Velg minst én butikk i sidepanelet.")
        else:
            # Browser-side prisanalyse
            items_json = json.dumps(items)
            fav_json   = json.dumps(st.session_state.favoritter)
            stores_json = json.dumps({k: v for k, v in STORES.items()})

            analyse_html = f"""
            <!DOCTYPE html><html><head><meta charset="utf-8">
            <style>
            * {{ box-sizing:border-box; margin:0; padding:0; }}
            body {{ background:transparent; font-family:'DM Sans',sans-serif; color:#fff; }}
            button.analyse {{
              width:100%; background:#6c63ff; color:#fff; border:none;
              border-radius:10px; font-weight:700; font-size:14px; letter-spacing:0.06em;
              padding:12px; cursor:pointer; transition:background 0.15s; margin-bottom:12px;
            }}
            button.analyse:hover {{ background:#5a52e0; }}
            button.analyse:disabled {{ background:#2a2a3a; color:#555; cursor:not-allowed; }}
            .status {{ color:#555; font-size:12px; margin-bottom:12px; min-height:16px; }}
            .section {{ margin-bottom:20px; }}
            .section h3 {{ font-size:13px; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:#555; margin-bottom:10px; }}
            .store-row {{ background:#0f0f1a; border:1px solid #1a1a2e; border-radius:10px; padding:10px 14px; margin-bottom:6px; display:flex; align-items:center; gap:10px; }}
            .store-row.best {{ border-color:#6c63ff; background:linear-gradient(135deg,#0f0f1a,#16123a); }}
            .store-name {{ flex:1; font-weight:600; font-size:14px; }}
            .store-found {{ font-size:11px; color:#555; }}
            .store-price {{ font-weight:700; font-size:15px; }}
            .badge {{ background:#6c63ff; color:#fff; padding:2px 8px; border-radius:20px; font-size:11px; font-weight:700; }}
            .diff {{ color:#ef4444; font-size:13px; }}
            .savings {{ background:linear-gradient(135deg,#091a12,#0b1f14); border:1px solid #1e4d33; border-radius:12px; padding:14px 18px; margin:10px 0; }}
            .savings-num {{ font-size:2.2rem; font-weight:800; color:#4ade80; line-height:1; }}
            .savings-label {{ color:#555; font-size:12px; margin-top:4px; }}
            .split-cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:10px; margin-top:10px; }}
            .split-card {{ background:#0f0f1a; border:1px solid #1a1a2e; border-radius:10px; padding:12px; }}
            .split-card-name {{ font-weight:700; font-size:13px; margin-bottom:4px; }}
            .split-card-price {{ font-size:1.3rem; font-weight:800; color:#6c63ff; margin-bottom:8px; }}
            .split-item {{ font-size:11px; color:#666; margin-bottom:2px; }}
            </style>
            </head><body>

            <button class="analyse" id="analyseBtn" onclick="runAnalyse()">🚀 Analyser priser</button>
            <div class="status" id="status"></div>
            <div id="output"></div>

            <script>
            const API_KEY   = "{KASSALAPP_API_KEY}";
            const items     = {items_json};
            const preferred = {fav_json};
            const stores    = {stores_json};
            const kombiner  = {'true' if kombiner else 'false'};
            const maks      = {maks};

            function sname(c) {{ return (stores[c] && stores[c].name) ? stores[c].name : c; }}
            function semoji(c) {{ return (stores[c] && stores[c].emoji) ? stores[c].emoji : "🏪"; }}

            async function runAnalyse() {{
              const btn    = document.getElementById("analyseBtn");
              const status = document.getElementById("status");
              const output = document.getElementById("output");
              btn.disabled = true; btn.textContent = "Henter priser...";
              status.textContent = ""; output.innerHTML = "";

              const eans = items.map(i => i.ean).filter(Boolean);
              if (!eans.length) {{ status.textContent = "Ingen EAN-koder."; btn.disabled=false; btn.textContent="🚀 Analyser priser"; return; }}

              try {{
                const resp = await fetch("https://kassal.app/api/v1/products/prices-bulk", {{
                  method: "POST",
                  headers: {{
                    "Authorization": `Bearer ${{API_KEY}}`,
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                  }},
                  body: JSON.stringify({{ eans, days: 7, aggregation: "min" }})
                }});

                if (!resp.ok) {{ status.textContent = `Feil: ${{resp.status}}`; return; }}
                const data = await resp.json();
                const bulk = data.data || [];

                if (!bulk.length) {{ status.textContent = "Ingen prisdata funnet."; return; }}

                // Bygg prislookup: ean → store → pris
                const prices = {{}};
                bulk.forEach(p => {{
                  prices[p.ean] = {{}};
                  (p.stores || []).forEach(s => {{
                    if (s.store && s.current_price != null)
                      prices[p.ean][s.store] = parseFloat(s.current_price);
                  }});
                }});

                // Finn aktive butikker
                const allStores = new Set();
                Object.values(prices).forEach(d => Object.keys(d).forEach(s => allStores.add(s)));
                const prefSet = new Set(preferred.filter(s => allStores.has(s)));
                const active  = prefSet.size ? prefSet : allStores;

                // Ranger enkeltbutikker
                const ranking = [];
                active.forEach(code => {{
                  let tot = 0, found = 0;
                  items.forEach(item => {{
                    if (!item.ean) return;
                    const p = (prices[item.ean] || {{}})[code];
                    if (p != null) {{ tot += p * (item.quantity || 1); found++; }}
                  }});
                  if (found) ranking.push({{ code, name: sname(code), emoji: semoji(code), total: Math.round(tot*100)/100, found }});
                }});
                ranking.sort((a,b) => a.total - b.total);

                let html = "";

                // Beste enkeltbutikk
                html += `<div class="section"><h3>🏪 Beste enkeltbutikk</h3>`;
                const medals = ["🥇","🥈","🥉","4.","5."];
                ranking.slice(0,5).forEach((r,i) => {{
                  const isBest = i === 0;
                  html += `<div class="store-row ${{isBest?'best':''}}">
                    <div>
                      <div class="store-name">${{medals[i]}} ${{r.emoji}} ${{r.name}}</div>
                      <div class="store-found">${{r.found}}/${{eans.length}} varer funnet</div>
                    </div>
                    <div class="store-price">${{r.total.toFixed(2)}} kr</div>
                    ${{isBest
                      ? `<span class="badge">✓ Billigst</span>`
                      : `<span class="diff">+${{(r.total - ranking[0].total).toFixed(2)}} kr</span>`
                    }}
                  </div>`;
                }});
                html += `</div>`;

                // Kombinert optimalisering
                if (kombiner && maks > 1 && ranking.length > 1) {{
                  // Greedy split
                  let asgn = items.map(item => {{
                    if (!item.ean) return null;
                    const valid = {{}};
                    active.forEach(c => {{ const p=(prices[item.ean]||{{}})[c]; if(p!=null) valid[c]=p; }});
                    if (!Object.keys(valid).length) return null;
                    const best = Object.entries(valid).sort((a,b)=>a[1]-b[1])[0];
                    return {{ name: item.name, qty: item.quantity||1, code: best[0], price: Math.round(best[1]*(item.quantity||1)*100)/100, valid }};
                  }}).filter(Boolean);

                  // Reduser til maks butikker
                  while (new Set(asgn.map(a=>a.code)).size > maks) {{
                    const unique = [...new Set(asgn.map(a=>a.code))];
                    const counts = {{}};
                    unique.forEach(s => counts[s] = asgn.filter(a=>a.code===s).length);
                    const smallest = unique.sort((a,b)=>counts[a]-counts[b])[0];
                    const rest = unique.filter(s=>s!==smallest);
                    asgn.forEach(a => {{
                      if (a.code !== smallest) return;
                      const cands = Object.entries(a.valid).filter(([s])=>rest.includes(s));
                      if (cands.length) {{
                        const best = cands.sort((a,b)=>a[1]-b[1])[0];
                        a.code  = best[0];
                        a.price = Math.round(best[1]*a.qty*100)/100;
                      }}
                    }});
                    if (!rest.length) break;
                  }});

                  const totalOpt = asgn.reduce((s,a)=>s+a.price, 0);
                  const bespar   = Math.round((ranking[0].total - totalOpt)*100)/100;

                  html += `<div class="section"><h3>🔀 Optimal fordeling (${{maks}} butikker)</h3>`;
                  if (bespar > 0.5) {{
                    html += `<div class="savings">
                      <div style="color:#4ade80;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:4px">Du sparer</div>
                      <div class="savings-num">${{bespar.toFixed(2)}} kr</div>
                      <div class="savings-label">mot å handle alt på ${{ranking[0].name}}</div>
                    </div>`;
                  }} else {{
                    html += `<p style="color:#555;font-size:13px">Minimal besparelse (${{bespar.toFixed(2)}} kr). Enklest å handle alt på ${{ranking[0].name}}.</p>`;
                  }}

                  // Grupper per butikk
                  const groups = {{}};
                  asgn.forEach(a => {{ if (!groups[a.code]) groups[a.code]=[]; groups[a.code].push(a); }});
                  html += `<div class="split-cards">`;
                  Object.entries(groups).forEach(([code, varer]) => {{
                    const sub = varer.reduce((s,v)=>s+v.price,0);
                    html += `<div class="split-card">
                      <div class="split-card-name">${{semoji(code)}} ${{sname(code)}}</div>
                      <div class="split-card-price">${{sub.toFixed(2)}} kr</div>
                      ${{varer.map(v=>`<div class="split-item">· ${{v.name}} × ${{v.qty}} — ${{v.price.toFixed(2)}} kr</div>`).join("")}}
                    </div>`;
                  }});
                  html += `</div></div>`;
                }}

                output.innerHTML = html;
                status.textContent = "✓ Analyse fullført";

              }} catch(e) {{
                status.textContent = "Nettverksfeil – prøv igjen.";
                console.error(e);
              }} finally {{
                btn.disabled = false;
                btn.textContent = "🚀 Analyser priser";
              }}
            }}
            </script>
            </body></html>
            """

            components.html(analyse_html, height=900, scrolling=True)
