"""SOS Calling. Never dials automatically and never claims a call was placed."""
from __future__ import annotations

import time

import streamlit as st

import config

def _qr_svg(tel: str):
    try:
        import segno
        return segno.make(f"tel:{tel}", error="m").svg_inline(scale=4, border=2, dark="#0d2b36")
    except Exception:
        return None


INSTRUCTIONS = ("Set SAFEROUTE_EMERGENCY_NUMBER in the environment or in .streamlit/secrets.toml. "
                "SafeRoute will not guess a number.")


def sos_dialog_content() -> None:
    tel = config.get_emergency_tel()
    if tel is None:
        st.warning("No emergency number is configured.")
        st.write(INSTRUCTIONS)
        _setup_hint()
        return
    st.markdown(f"**{config.EMERGENCY_NUMBER_LABEL}**")
    st.code(tel, language=None)
    st.write("The button below asks your device to open its dialer. You must press call yourself.")
    st.info("This is a dialer shortcut, not an emergency-dispatch integration. SafeRoute does not notify "
            "or send an ambulance, police or fire brigade.")
    ack = st.checkbox("I understand I must complete the call myself.", key="sos_ack")
    c1, c2 = st.columns(2)
    if c1.button("Cancel", key="sos_cancel", use_container_width=True):
        st.rerun()  # closes the dialog; nothing is dialed
    if ack:  # a plain link opens the dialer directly; link_button would open a blank tab on desktop
        c2.markdown(f'<a class="sr-call" href="tel:{tel}">Confirm and open dialer</a>', unsafe_allow_html=True)
    else:
        c2.button("Confirm and open dialer", key="sos_confirm_disabled", disabled=True, use_container_width=True)
    qr = _qr_svg(tel)
    if qr:
        with st.expander("Calling from a computer? Scan with your phone"):
            st.image(qr, width=170)
            st.caption("Scanning opens your phone's dialer with this number. You still press call yourself.")
    st.caption("If nothing happens, dial the number manually. On a desktop browser without a phone app the "
               "dialer link may do nothing, so call from a phone. SafeRoute cannot tell whether a call was placed.")


def _setup_hint() -> None:
    """Show where the app looks for the number so a wrong path or file name is easy to spot."""
    from pathlib import Path
    secrets = Path.cwd() / ".streamlit" / "secrets.toml"
    raw = config._setting("SAFEROUTE_EMERGENCY_NUMBER")
    if raw:
        st.caption("A value was found for SAFEROUTE_EMERGENCY_NUMBER, but it is not a valid phone number. "
                   "Use digits only, for example 112 or +911234567890.")
    st.caption(f"Secrets file expected at: {secrets} ({'found' if secrets.exists() else 'not found'}).")
    if secrets.with_name("secrets.toml.txt").exists():
        st.caption("Found secrets.toml.txt. Rename it to secrets.toml, without the .txt ending.")
    st.caption("After saving the file, close this dialog and reopen SOS Calling. If it still fails, "
               "stop the app (Ctrl+C) and start it again from the project folder.")


@st.dialog("SOS Calling")
def _sos_dialog() -> None:
    sos_dialog_content()


def render_sos_button() -> None:
    with st.container(key="sos_container"):
        clicked = st.button("SOS Calling", icon=":material/emergency:", key="sos_open",
                            help="Opens a confirmation step. Nothing is dialed automatically.")
    if clicked:
        now = time.monotonic()
        last = st.session_state.get("sos_last_open")
        if last is None or now - last >= config.SOS_DEBOUNCE_S:
            st.session_state["sos_last_open"] = now
            st.session_state["sos_ack"] = False
            _sos_dialog()
