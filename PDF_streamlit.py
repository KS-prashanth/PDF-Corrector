import base64
import os

import pandas as pd
import streamlit as st

from PDF_core import process_pdf_bytes

st.set_page_config(page_title="PDF Corrector", page_icon="📄", layout="wide")


def show_pdf(pdf_bytes, height=650):
    """Embeds a PDF (from bytes) inline using a base64 iframe."""
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_display = f"""
        <iframe
            src="data:application/pdf;base64,{b64}"
            width="100%"
            height="{height}"
            type="application/pdf"
            style="border: 1px solid #444; border-radius: 6px;"
        ></iframe>
    """
    st.markdown(pdf_display, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar — API key handling
# ---------------------------------------------------------------------------

st.sidebar.title("Settings")

env_key = os.environ.get("OPENAI_API_KEY", "")
api_key_input = st.sidebar.text_input(
    "OpenAI API Key",
    value=env_key,
    type="password",
    help="Reads from OPENAI_API_KEY env var if set. You can override it here for this session only.",
)
if api_key_input:
    os.environ["OPENAI_API_KEY"] = api_key_input

st.sidebar.caption(
    "Your key is only kept in this session's memory — it is not saved to disk."
)

# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

st.title("📄 PDF Spelling & Grammar Corrector")
st.write(
    "Upload a PDF (best for documents exported from Word or Google Docs). "
    "Click **Generate** to fix spelling/grammar, preserve the original layout, "
    "and append a short summary page."
)

uploaded_file = st.file_uploader("Upload a PDF", type=["pdf"])

if "output_bytes" not in st.session_state:
    st.session_state.output_bytes = None
    st.session_state.corrections = None
    st.session_state.summary = None

if uploaded_file is not None:
    input_bytes = uploaded_file.read()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Original PDF")
        show_pdf(input_bytes)

    generate_clicked = st.button("✨ Generate", type="primary", use_container_width=False)

    if generate_clicked:
        if not os.environ.get("OPENAI_API_KEY"):
            st.error("Please enter your OpenAI API key in the sidebar first.")
        else:
            status_box = st.empty()
            log_lines = []

            def report(msg):
                log_lines.append(msg)
                status_box.info("\n\n".join(log_lines[-5:]))

            with st.spinner("Processing PDF..."):
                try:
                    output_bytes, corrections, summary = process_pdf_bytes(
                        input_bytes, progress_callback=report
                    )
                    st.session_state.output_bytes = output_bytes
                    st.session_state.corrections = corrections
                    st.session_state.summary = summary
                    status_box.success("Done!")
                except Exception as e:
                    status_box.error(f"Something went wrong: {e}")

    # -----------------------------------------------------------------------
    # Results: corrections table, summary, output PDF
    # -----------------------------------------------------------------------

    if st.session_state.output_bytes is not None:
        st.divider()

        st.subheader("Corrections made")
        if st.session_state.corrections:
            df = pd.DataFrame(st.session_state.corrections)
            df = df.rename(columns={
                "page": "Page",
                "original": "Original (incorrect)",
                "corrected": "Corrected",
            })
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"{len(st.session_state.corrections)} correction(s) made.")
        else:
            st.info("No spelling or grammar issues were found.")

        st.subheader("Summary")
        st.write(st.session_state.summary)

        st.divider()

        with col2:
            st.subheader("Corrected PDF")
            show_pdf(st.session_state.output_bytes)

        st.download_button(
            label="⬇️ Download corrected PDF",
            data=st.session_state.output_bytes,
            file_name="corrected_output.pdf",
            mime="application/pdf",
        )
else:
    st.session_state.output_bytes = None
    st.session_state.corrections = None
    st.session_state.summary = None