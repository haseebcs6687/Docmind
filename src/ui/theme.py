"""Theme injection helper for DocMind Streamlit UI."""

from pathlib import Path
import streamlit as st

THEME_DIR = Path(__file__).resolve().parent
STYLES_FILE = THEME_DIR / "styles.css"


def inject_custom_theme() -> None:
    """Inject global CSS styles from styles.css into the active Streamlit app."""
    if not STYLES_FILE.exists():
        return
    css_content = STYLES_FILE.read_text(encoding="utf-8")
    st.markdown(
        f"<!-- docmind-injected-styles -->\n<style>\n{css_content}\n</style>",
        unsafe_allow_html=True,
    )
