from __future__ import annotations

from html import escape

import streamlit as st


RISK_COLORS = {
    "HEALTHY": "#15803D",
    "WATCH": "#CA8A04",
    "RISK": "#EA580C",
    "CRITICAL": "#DC2626",
    "UNKNOWN": "#64748B",
}


def inject_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
          --sp-bg: #F4F7FB;
          --sp-surface: #FFFFFF;
          --sp-border: #E2E8F0;
          --sp-text: #0F172A;
          --sp-muted: #64748B;
          --sp-blue: #2563EB;
          --sp-blue-soft: #EFF6FF;
          --sp-green: #15803D;
          --sp-yellow: #CA8A04;
          --sp-orange: #EA580C;
          --sp-red: #DC2626;
          --sp-gray: #64748B;
        }
        .stApp { background: var(--sp-bg); color: var(--sp-text); }
        [data-testid="stHeader"] { background: rgba(244, 247, 251, 0.88); }
        [data-testid="stToolbar"], [data-testid="stStatusWidget"], #MainMenu, footer { visibility:hidden; }
        [data-testid="stDecoration"] { display:none; }
        [data-testid="stMainBlockContainer"] {
          max-width: 1480px;
          padding-top: 1.65rem;
          padding-bottom: 3rem;
        }
        [data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid var(--sp-border); }
        [data-testid="stSidebar"] [data-testid="stRadio"] label,
        [data-testid="stSidebar"] [data-testid="stSelectbox"] label { font-weight: 600; }
        h1, h2, h3 { color: var(--sp-text); letter-spacing: -0.02em; }
        h1 { font-size: 2rem !important; }
        h2 { font-size: 1.3rem !important; }
        h3 { font-size: 1.02rem !important; }
        .sp-sidebar-brand { display:flex; gap:.7rem; align-items:center; padding:.25rem 0 1.2rem; }
        .sp-sidebar-brand strong { display:block; font-size:1.05rem; color:var(--sp-text); }
        .sp-sidebar-brand span { display:block; color:var(--sp-muted); font-size:.72rem; margin-top:.12rem; }
        .sp-brand-mark { width:2.25rem; height:2.25rem; border-radius:.65rem; display:grid; place-items:center; background:#0F172A; color:white; font-weight:800; font-size:.78rem; }
        .sp-eyebrow { color:var(--sp-blue); text-transform:uppercase; font-weight:800; letter-spacing:.11em; font-size:.7rem; margin-bottom:.35rem; }
        .sp-page-head { display:flex; align-items:flex-start; justify-content:space-between; gap:1.5rem; margin-bottom:1rem; }
        .sp-page-head h1 { margin:.05rem 0 .35rem; }
        .sp-page-head p { margin:0; color:var(--sp-muted); max-width:850px; }
        .sp-meta { color:var(--sp-muted); font-size:.76rem; text-align:right; line-height:1.6; white-space:nowrap; }
        .sp-demo-pill { display:inline-flex; align-items:center; border:1px solid #BFDBFE; color:#1D4ED8; background:#EFF6FF; padding:.18rem .5rem; border-radius:999px; font-size:.7rem; font-weight:700; }
        .sp-card { background:var(--sp-surface); border:1px solid var(--sp-border); border-radius:14px; padding:1rem 1.05rem; box-shadow:0 1px 2px rgba(15,23,42,.035); }
        .sp-section-title { display:flex; justify-content:space-between; gap:1rem; align-items:end; margin:.2rem 0 .65rem; }
        .sp-section-title h2 { margin:0; }
        .sp-section-title span { color:var(--sp-muted); font-size:.75rem; }
        .sp-kpi { min-height:128px; position:relative; overflow:hidden; }
        .sp-kpi:before { content:""; position:absolute; left:0; right:0; top:0; height:3px; background:var(--sp-accent, var(--sp-blue)); }
        .sp-kpi-label { color:var(--sp-muted); font-size:.76rem; font-weight:700; letter-spacing:.015em; }
        .sp-kpi-value { color:var(--sp-text); font-size:1.72rem; font-weight:800; margin:.42rem 0 .26rem; letter-spacing:-.035em; }
        .sp-kpi-detail { color:var(--sp-muted); font-size:.74rem; line-height:1.35; }
        .sp-badge { display:inline-flex; align-items:center; gap:.35rem; padding:.2rem .52rem; border-radius:999px; font-weight:800; font-size:.68rem; border:1px solid currentColor; }
        .sp-dot { width:.38rem; height:.38rem; border-radius:999px; background:currentColor; }
        .sp-insight { min-height:155px; }
        .sp-insight h3 { margin:.6rem 0 .45rem; }
        .sp-insight p { margin:.22rem 0; color:var(--sp-muted); font-size:.82rem; line-height:1.5; }
        .sp-insight strong { color:var(--sp-text); }
        .sp-action-title { display:flex; justify-content:space-between; gap:1rem; align-items:center; }
        .sp-action-title h3 { margin:0; }
        .sp-action-type { color:#1D4ED8; background:#EFF6FF; border:1px solid #BFDBFE; border-radius:8px; padding:.25rem .5rem; font-size:.68rem; font-weight:800; }
        .sp-action-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.65rem; margin:.85rem 0; }
        .sp-action-cell { background:#F8FAFC; border:1px solid var(--sp-border); border-radius:10px; padding:.65rem; }
        .sp-action-cell span { display:block; color:var(--sp-muted); font-size:.68rem; }
        .sp-action-cell strong { display:block; color:var(--sp-text); font-size:.9rem; margin-top:.15rem; }
        .sp-evidence-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.65rem; }
        .sp-evidence { border-left:3px solid var(--sp-blue); background:#F8FAFC; border-radius:0 10px 10px 0; padding:.65rem .75rem; }
        .sp-evidence span { display:block; color:var(--sp-muted); font-size:.68rem; }
        .sp-evidence strong { display:block; margin-top:.12rem; font-size:.88rem; }
        .sp-flow { display:flex; align-items:center; gap:.35rem; flex-wrap:wrap; color:var(--sp-muted); font-size:.72rem; margin:.65rem 0; }
        .sp-flow b { color:var(--sp-text); background:#F8FAFC; border:1px solid var(--sp-border); padding:.28rem .48rem; border-radius:8px; }
        .sp-callout { border-left:4px solid var(--sp-blue); background:#EFF6FF; border-radius:0 12px 12px 0; padding:.78rem .9rem; color:#1E3A8A; font-size:.8rem; }
        .sp-warning { border-left-color:var(--sp-orange); background:#FFF7ED; color:#9A3412; }
        .sp-subtle { color:var(--sp-muted); font-size:.74rem; }
        [data-testid="stDataFrame"] { border:1px solid var(--sp-border); border-radius:12px; overflow:hidden; }
        [data-testid="stMetric"] { background:#FFFFFF; border:1px solid var(--sp-border); border-radius:12px; padding:.75rem; }
        [data-testid="stBaseButton-primary"], button[kind="primary"] {
          background:var(--sp-blue) !important;
          border-color:var(--sp-blue) !important;
          color:#FFFFFF !important;
        }
        div[data-testid="stDialog"] div[role="dialog"] { margin-left:auto; margin-right:0; min-height:100vh; border-radius:18px 0 0 18px; }
        @media (max-width: 1050px) {
          .sp-action-grid, .sp-evidence-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
          .sp-page-head { display:block; }
          .sp-meta { text-align:left; margin-top:.5rem; }
        }
        @media (max-width: 720px) {
          [data-testid="stMainBlockContainer"] { padding-left:1rem; padding-right:1rem; }
          [data-testid="stHorizontalBlock"] { flex-direction:column !important; gap:.75rem !important; }
          [data-testid="stColumn"] { width:100% !important; flex:1 1 100% !important; }
          .sp-action-grid, .sp-evidence-grid { grid-template-columns:1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str, *, eyebrow: str, meta: str = "") -> None:
    st.markdown(
        f"""
        <div class="sp-page-head">
          <div>
            <div class="sp-eyebrow">{escape(eyebrow)}</div>
            <h1>{escape(title)}</h1>
            <p>{escape(subtitle)}</p>
          </div>
          <div class="sp-meta"><span class="sp-demo-pill">SYNTHETIC DEMO</span><br>{escape(meta)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str, caption: str = "") -> None:
    st.markdown(
        f'<div class="sp-section-title"><h2>{escape(title)}</h2><span>{escape(caption)}</span></div>',
        unsafe_allow_html=True,
    )
