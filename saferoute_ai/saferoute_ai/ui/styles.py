import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, select, textarea { font-family: 'IBM Plex Sans', system-ui, sans-serif !important; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1600px; }
footer, #MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

[data-testid="stSidebar"] { background: #fbfcfd; border-right: 1px solid #d5dce2; }
.side-title { font-size: 1.05rem; font-weight: 600; color: #14232b; margin: 0 0 .15rem 0; }
.side-sub { font-size: .82rem; color: #5b6b75; margin-bottom: .6rem; }
.group { font-size: .86rem; font-weight: 600; color: #0f5c6e; border-bottom: 1px solid #d5dce2; padding: .9rem 0 .3rem 0; margin-bottom: .5rem; }
.field { font-size: .82rem; font-weight: 500; color: #33454f; margin: .5rem 0 .15rem 0; }

.hdr { display: flex; justify-content: space-between; align-items: center; gap: 1.5rem;
  background: #0d2b36; color: #eaf1f4; padding: 1.1rem 1.4rem; border-radius: 4px; border-left: 6px solid #e8820c; }
.hdr h1 { font-size: 1.55rem; font-weight: 600; margin: 0; letter-spacing: -.01em; color: #fff; padding: 0; }
.hdr p { margin: .25rem 0 0 0; font-size: .9rem; color: #a9bec7; max-width: 62ch; }
.status { text-align: right; min-width: 15rem; }
.status .lbl { font-size: .78rem; color: #a9bec7; margin-bottom: .2rem; }
.status .val { font-size: 1rem; font-weight: 600; display: inline-flex; align-items: center; gap: .5rem; }
.dot { width: .7rem; height: .7rem; border-radius: 50%; display: inline-block; }

.sim { margin: .8rem 0; padding: .65rem .9rem; background: #fff4e0; border: 1px solid #f0c987; border-left: 5px solid #e8820c;
  font-size: .88rem; color: #5a3b05; border-radius: 3px; }
.sim b { color: #3f2800; }
.note { margin: .5rem 0; padding: .55rem .9rem; background: #fff; border: 1px solid #d5dce2; border-left: 5px solid #7b8794; font-size: .86rem; color: #33454f; border-radius: 3px; }
.err { margin: .8rem 0; padding: .7rem .9rem; background: #fdecec; border: 1px solid #f1b4b4; border-left: 5px solid #c62828; font-size: .9rem; color: #6b1414; border-radius: 3px; }

.rc { background: #fff; border: 1px solid #d5dce2; border-left: 6px solid var(--accent, #c2cad1); border-radius: 3px; padding: .85rem 1rem; height: 100%; }
.rc .top { display: flex; align-items: center; justify-content: space-between; margin-bottom: .35rem; }
.rc .name { font-weight: 600; font-size: .95rem; color: #14232b; }
.rc .tag { font-size: .76rem; color: #33454f; background: #eef1f4; padding: .1rem .5rem; border-radius: 2px; }
.rc .eta { font-size: 2.1rem; font-weight: 600; line-height: 1.1; color: #14232b; font-variant-numeric: tabular-nums; }
.rc .eta small { font-size: .9rem; font-weight: 500; color: #5b6b75; margin-left: .2rem; }
.rc .kv { display: flex; justify-content: space-between; font-size: .88rem; color: #33454f; padding: .22rem 0; border-top: 1px solid #edf0f3; }
.rc .kv b { font-weight: 600; color: #14232b; font-variant-numeric: tabular-nums; }
.bar { height: 6px; background: #e4e9ed; border-radius: 3px; margin-top: .35rem; overflow: hidden; }
.bar i { display: block; height: 100%; }
.rc .msg { color: #5b6b75; font-size: .9rem; margin-top: .4rem; }

.panel { background: #fff; border: 1px solid #d5dce2; border-radius: 3px; padding: .9rem 1.1rem; margin-bottom: .8rem; }
.panel h3 { font-size: .98rem; font-weight: 600; margin: 0 0 .5rem 0; padding: 0; color: #14232b; }
.panel .kv { display: flex; justify-content: space-between; gap: 1rem; font-size: .88rem; padding: .28rem 0; border-top: 1px solid #edf0f3; color: #33454f; }
.panel .kv b { color: #14232b; font-weight: 500; text-align: right; }
.panel .big { font-size: 1.35rem; font-weight: 600; color: #14232b; font-variant-numeric: tabular-nums; }
.panel .sub { font-size: .85rem; color: #5b6b75; margin-top: .15rem; }
.bad { color: #b3261e !important; } .ok { color: #1b7a3d !important; } .warn { color: #a85f00 !important; }

.section { font-size: 1.02rem; font-weight: 600; color: #14232b; margin: 1.1rem 0 .5rem 0; }
div[data-testid="stButton"] button[kind="primary"] { background: #0f5c6e; border: 1px solid #0f5c6e; border-radius: 3px; font-weight: 600; }
div[data-testid="stButton"] button[kind="primary"]:hover { background: #0b4756; border-color: #0b4756; }
:focus-visible { outline: 2px solid #1d5fd1 !important; outline-offset: 2px; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
