import streamlit as st

st.set_page_config(
    layout="wide",
    page_title="Migration Oracle",
    page_icon="⚗️",
)

st.markdown("""
<style>
/* ─── Google Fonts ─────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

/* ─── Design Tokens ─────────────────────────────────────────── */
:root {
    --bg:            #0d0f14;
    --bg-surface:    #13161e;
    --bg-card:       #181c26;
    --bg-hover:      #1e2330;
    --border:        #252a38;
    --border-bright: #2e3547;
    --accent:        #4ade9e;
    --accent-dim:    #1a4a35;
    --accent-text:   #0d2b1f;
    --warning:       #f5a623;
    --warning-dim:   #3a2800;
    --danger:        #f87171;
    --danger-dim:    #3b0f0f;
    --info:          #60a5fa;
    --info-dim:      #0f2444;
    --muted:         #5a6278;
    --text:          #e8eaf0;
    --text-secondary:#9aa0b8;
    --radius:        10px;
    --radius-lg:     14px;
    --font-ui:       'DM Sans', sans-serif;
    --font-display:  'Syne', sans-serif;
    --font-mono:     'IBM Plex Mono', monospace;
}

/* ─── Global Reset ──────────────────────────────────────────── */
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: var(--font-ui) !important;
}

/* ─── Sidebar ────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * {
    color: var(--text) !important;
    font-family: var(--font-ui) !important;
}
[data-testid="stSidebarNav"] a {
    border-radius: var(--radius) !important;
    padding: 8px 12px !important;
    margin: 2px 8px !important;
    font-size: 13.5px !important;
    transition: background 0.15s ease !important;
}
[data-testid="stSidebarNav"] a:hover {
    background: var(--bg-hover) !important;
}
[data-testid="stSidebarNav"] a[aria-selected="true"] {
    background: var(--accent-dim) !important;
    color: var(--accent) !important;
}

/* ─── Page Titles ───────────────────────────────────────────── */
h1 {
    font-family: var(--font-display) !important;
    font-size: 28px !important;
    font-weight: 800 !important;
    letter-spacing: -0.5px !important;
    color: var(--text) !important;
    padding-bottom: 0.25rem !important;
    border-bottom: 1px solid var(--border) !important;
    margin-bottom: 1.5rem !important;
}
h2 {
    font-family: var(--font-display) !important;
    font-weight: 600 !important;
    font-size: 18px !important;
    color: var(--text) !important;
    letter-spacing: -0.2px !important;
}
h3 { font-size: 15px !important; font-weight: 500 !important; }

/* ─── Buttons ───────────────────────────────────────────────── */
.stButton > button {
    background: var(--bg-card) !important;
    color: var(--text) !important;
    border: 1px solid var(--border-bright) !important;
    border-radius: var(--radius) !important;
    font-family: var(--font-ui) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 0.4rem 1rem !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover {
    background: var(--bg-hover) !important;
    border-color: var(--accent) !important;
    color: var(--accent) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="primary"],
.stFormSubmitButton > button {
    background: var(--accent) !important;
    color: var(--accent-text) !important;
    border-color: var(--accent) !important;
    font-weight: 600 !important;
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button:hover {
    opacity: 0.88 !important;
    color: var(--accent-text) !important;
    transform: translateY(-1px) !important;
}

/* ─── Inputs ────────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div {
    background: var(--bg-card) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    font-family: var(--font-ui) !important;
    font-size: 13.5px !important;
    transition: border-color 0.15s !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px var(--accent-dim) !important;
}
input::placeholder, textarea::placeholder {
    color: var(--muted) !important;
}

/* ─── Labels ───────────────────────────────────────────────── */
label, .stSelectbox label, .stTextInput label, .stTextArea label {
    color: var(--text-secondary) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    font-family: var(--font-mono) !important;
}

/* ─── Metrics ───────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 1rem 1.25rem !important;
}
[data-testid="stMetricLabel"] {
    color: var(--text-secondary) !important;
    font-family: var(--font-mono) !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}
[data-testid="stMetricValue"] {
    color: var(--accent) !important;
    font-family: var(--font-display) !important;
    font-size: 32px !important;
    font-weight: 700 !important;
}

/* ─── Alerts / Banners ──────────────────────────────────────── */
.stAlert {
    background: var(--bg-card) !important;
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
    font-size: 13.5px !important;
}
[data-testid="stAlertContentInfo"]    { border-left: 3px solid var(--info) !important; }
[data-testid="stAlertContentSuccess"] { border-left: 3px solid var(--accent) !important; }
[data-testid="stAlertContentError"]   { border-left: 3px solid var(--danger) !important; }
[data-testid="stAlertContentWarning"] { border-left: 3px solid var(--warning) !important; }

/* ─── Tabs ──────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--text-secondary) !important;
    font-family: var(--font-ui) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    border-radius: var(--radius) var(--radius) 0 0 !important;
    padding: 8px 16px !important;
    border: none !important;
    transition: color 0.15s !important;
}
.stTabs [aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
    background: var(--accent-dim) !important;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--text) !important; }

/* ─── Expanders ─────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    color: var(--text) !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    padding: 10px 14px !important;
    transition: background 0.15s !important;
}
.streamlit-expanderHeader:hover { background: var(--bg-hover) !important; }
.streamlit-expanderContent {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border) !important;
    border-top: none !important;
    border-radius: 0 0 var(--radius) var(--radius) !important;
    padding: 1rem !important;
}

/* ─── Containers ─────────────────────────────────────────────── */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 1rem 1.25rem !important;
    margin-bottom: 0.75rem !important;
}

/* ─── Divider ───────────────────────────────────────────────── */
hr {
    border-color: var(--border) !important;
    margin: 1.25rem 0 !important;
}

/* ─── Code Blocks ───────────────────────────────────────────── */
code, pre {
    font-family: var(--font-mono) !important;
    background: var(--bg-card) !important;
    color: var(--accent) !important;
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
    font-size: 12.5px !important;
}

/* ─── Selectbox Dropdown ─────────────────────────────────────── */
[data-baseweb="popover"] {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-bright) !important;
    border-radius: var(--radius) !important;
}
[data-baseweb="menu"] li {
    color: var(--text) !important;
    font-size: 13.5px !important;
}
[data-baseweb="menu"] li:hover { background: var(--bg-hover) !important; }

/* ─── Caption / Caption text ─────────────────────────────────── */
.stCaption, small, [data-testid="stCaptionContainer"] {
    color: var(--text-secondary) !important;
    font-size: 12px !important;
    font-family: var(--font-mono) !important;
}

/* ─── Checkbox ───────────────────────────────────────────────── */
.stCheckbox label { text-transform: none !important; font-size: 13.5px !important; }

/* ─── Scrollbar ──────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg) }
::-webkit-scrollbar-thumb { background: var(--border-bright); border-radius: 3px; }

/* ─── Sidebar branding ───────────────────────────────────────── */
.sidebar-brand {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 800;
    color: var(--accent);
    letter-spacing: -0.3px;
    padding: 1rem 1rem 0.5rem;
    display: flex;
    align-items: center;
    gap: 8px;
}
.sidebar-brand span {
    font-size: 11px;
    font-weight: 400;
    font-family: var(--font-mono);
    color: var(--muted);
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 6px;
    letter-spacing: 0.04em;
}
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown("""
<div class="sidebar-brand">
  ⚗️ Migration Oracle <span>v1.0</span>
</div>
""", unsafe_allow_html=True)