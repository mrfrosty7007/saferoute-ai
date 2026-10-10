import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

/* Global Font and Layout */
html, body, [class*="css"], .stMarkdown, button, input, select, textarea {
    font-family: 'IBM Plex Sans', system-ui, -apple-system, sans-serif !important;
}

html, body {
    background-color: #f4f6f8 !important;
    color: #14232b !important;
    overflow-x: hidden !important;
    margin: 0;
    padding: 0;
}

.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: #f4f6f8 !important;
    color: #14232b !important;
}

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
    max-width: 1600px;
}

footer, #MainMenu {
    visibility: hidden;
}

header[data-testid="stHeader"] {
    background: transparent !important;
}

/* Sidebar Container & Titles */
[data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
    background-color: #fbfcfd !important;
    border-right: 1px solid #d5dce2 !important;
}

.side-title {
    font-size: 1.10rem;
    font-weight: 700;
    color: #0d2b36 !important;
    margin: 0 0 .2rem 0;
    letter-spacing: -0.01em;
}

.side-sub {
    font-size: .84rem;
    color: #4a5c66 !important;
    margin-bottom: .8rem;
    line-height: 1.4;
}

.group {
    font-size: .86rem;
    font-weight: 700;
    color: #0f5c6e !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 2px solid #e1e7ec;
    padding: 1rem 0 .35rem 0;
    margin-bottom: .6rem;
}

.field {
    font-size: .84rem;
    font-weight: 600;
    color: #14232b !important;
    margin: .6rem 0 .2rem 0;
}

/* Sidebar Widgets Text Colors & High Contrast Overrides */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] span {
    color: #14232b !important;
}

[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
    color: #14232b !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
}

[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
[data-testid="stSidebar"] .stCaption {
    color: #4a5c66 !important;
    font-size: 0.80rem !important;
    line-height: 1.35 !important;
    margin-top: 0.15rem !important;
}

/* Radio buttons inside sidebar */
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label {
    color: #14232b !important;
    font-weight: 500 !important;
    font-size: 0.86rem !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] label p {
    color: #14232b !important;
    font-weight: 500 !important;
}

/* Selectboxes inside sidebar */
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] {
    background-color: #ffffff !important;
    border: 1px solid #c2cad1 !important;
    border-radius: 4px !important;
    color: #14232b !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] * {
    color: #14232b !important;
    font-size: 0.88rem !important;
}

/* Sliders inside sidebar */
[data-testid="stSidebar"] [data-testid="stSlider"] div[data-testid="stSliderThumbValue"] {
    color: #0f5c6e !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stTickBar"] div {
    color: #33454f !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
}
[data-testid="stSidebar"] [data-testid="stSlider"] div {
    color: #14232b !important;
}

/* Number inputs and Text inputs inside sidebar */
[data-testid="stSidebar"] input {
    background-color: #ffffff !important;
    color: #14232b !important;
    border: 1px solid #c2cad1 !important;
    border-radius: 4px !important;
}

/* Calculate Routes Button */
div[data-testid="stButton"] button[kind="primary"] {
    background-color: #0f5c6e !important;
    color: #ffffff !important;
    border: 1px solid #0f5c6e !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    padding: 0.55rem 1rem !important;
    letter-spacing: 0.01em !important;
    box-shadow: 0 1px 2px rgba(15,92,110,0.2) !important;
}
div[data-testid="stButton"] button[kind="primary"]:hover {
    background-color: #0b4756 !important;
    border-color: #0b4756 !important;
}

/* Header Banner */
.hdr {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1.5rem;
    background: #0d2b36;
    color: #eaf1f4;
    padding: 1.1rem 1.4rem;
    border-radius: 4px;
    border-left: 6px solid #e8820c;
    box-shadow: 0 2px 4px rgba(13,43,54,0.12);
}
.hdr h1 {
    font-size: 1.55rem;
    font-weight: 600;
    margin: 0;
    letter-spacing: -.01em;
    color: #ffffff !important;
    padding: 0;
}
.hdr p {
    margin: .25rem 0 0 0;
    font-size: .9rem;
    color: #a9bec7 !important;
    max-width: 68ch;
}
.status {
    text-align: right;
    min-width: 15rem;
}
.status .lbl {
    font-size: .78rem;
    color: #a9bec7 !important;
    margin-bottom: .2rem;
}
.status .val {
    font-size: 1rem;
    font-weight: 600;
    color: #ffffff !important;
    display: inline-flex;
    align-items: center;
    gap: .5rem;
}
.dot {
    width: .7rem;
    height: .7rem;
    border-radius: 50%;
    display: inline-block;
}

/* Informational Banners */
.sim {
    margin: .8rem 0;
    padding: .65rem .9rem;
    background: #fff4e0;
    border: 1px solid #f0c987;
    border-left: 5px solid #e8820c;
    font-size: .88rem;
    color: #5a3b05 !important;
    border-radius: 3px;
}
.sim b {
    color: #3f2800 !important;
}
.note {
    margin: .5rem 0;
    padding: .55rem .9rem;
    background: #ffffff;
    border: 1px solid #d5dce2;
    border-left: 5px solid #7b8794;
    font-size: .86rem;
    color: #33454f !important;
    border-radius: 3px;
}
.err {
    margin: .8rem 0;
    padding: .7rem .9rem;
    background: #fdecec;
    border: 1px solid #f1b4b4;
    border-left: 5px solid #c62828;
    font-size: .9rem;
    color: #6b1414 !important;
    border-radius: 3px;
}

/* Route Cards */
.rc {
    background: #ffffff;
    border: 1px solid #d5dce2;
    border-left: 6px solid var(--accent, #c2cad1);
    border-radius: 3px;
    padding: .85rem 1rem;
    height: 100%;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03);
}
.rc .top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: .35rem;
}
.rc .name {
    font-weight: 600;
    font-size: .95rem;
    color: #14232b !important;
}
.rc .tag {
    font-size: .76rem;
    color: #33454f !important;
    background: #eef1f4;
    padding: .1rem .5rem;
    border-radius: 2px;
}
.rc .eta {
    font-size: 2.1rem;
    font-weight: 600;
    line-height: 1.1;
    color: #14232b !important;
    font-variant-numeric: tabular-nums;
}
.rc .eta small {
    font-size: .9rem;
    font-weight: 500;
    color: #5b6b75 !important;
    margin-left: .2rem;
}
.rc .kv {
    display: flex;
    justify-content: space-between;
    font-size: .88rem;
    color: #33454f !important;
    padding: .22rem 0;
    border-top: 1px solid #edf0f3;
}
.rc .kv b {
    font-weight: 600;
    color: #14232b !important;
    font-variant-numeric: tabular-nums;
}
.bar {
    height: 6px;
    background: #e4e9ed;
    border-radius: 3px;
    margin-top: .35rem;
    overflow: hidden;
}
.bar i {
    display: block;
    height: 100%;
}
.rc .msg {
    color: #5b6b75 !important;
    font-size: .9rem;
    margin-top: .4rem;
}

/* Panels */
.panel {
    background: #ffffff;
    border: 1px solid #d5dce2;
    border-radius: 3px;
    padding: .9rem 1.1rem;
    margin-bottom: .8rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03);
}
.panel h3 {
    font-size: .98rem;
    font-weight: 600;
    margin: 0 0 .5rem 0;
    padding: 0;
    color: #14232b !important;
}
.panel .kv {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    font-size: .88rem;
    padding: .28rem 0;
    border-top: 1px solid #edf0f3;
    color: #33454f !important;
}
.panel .kv b {
    color: #14232b !important;
    font-weight: 500;
    text-align: right;
}
.panel .big {
    font-size: 1.35rem;
    font-weight: 600;
    color: #14232b !important;
    font-variant-numeric: tabular-nums;
}
.panel .sub {
    font-size: .85rem;
    color: #5b6b75 !important;
    margin-top: .15rem;
}
.bad { color: #b3261e !important; }
.ok { color: #1b7a3d !important; }
.warn { color: #a85f00 !important; }

/* Section Headings in Main Content */
.section {
    font-size: 1.05rem;
    font-weight: 700;
    color: #0d2b36 !important;
    margin: 1.2rem 0 .5rem 0;
    letter-spacing: -0.01em;
}

/* Main Area Radio buttons (e.g. Map View) */
[data-testid="stRadio"] [role="radiogroup"] label {
    color: #14232b !important;
    font-weight: 600 !important;
}
[data-testid="stRadio"] [role="radiogroup"] label p {
    color: #14232b !important;
    font-weight: 600 !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    background: #ffffff;
    border: 1px solid #d5dce2;
    border-radius: 4px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03);
}

:focus-visible {
    outline: 2px solid #1d5fd1 !important;
    outline-offset: 2px;
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
