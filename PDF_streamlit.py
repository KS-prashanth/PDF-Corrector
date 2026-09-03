
import base64
import os

import pandas as pd
import streamlit as st

from PDF_core import process_pdf_bytes

st.set_page_config(page_title="PDF Corrector", page_icon="📄", layout="wide")


def show_pdf(pdf_bytes, height=650):

    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_display = f"""
        <iframe
            src="data:application/pdf;base64,{b64}"
            width="100%"
            height="{height}"
            type="application/pdf"
            style="border: 1px solid #444; border-radius: 6px;"
        ></iframe>"""
        
    st.markdown(pdf_display, unsafe_allow_html=True)



st.sidebar.title("Settings")

try:
    default_key = st.secrets.get("OPENAI_API_KEY", "")
except Exception:
    default_key = ""
if not default_key:
    default_key = os.environ.get("OPENAI_API_KEY", "")

visitor_key = st.sidebar.text_input(
    "Use your own OpenAI API key (optional)",
    value="",
    type="password",
    help="Leave blank to use the app's default key. Enter your own to use your own quota instead.",
)

effective_api_key = visitor_key.strip() if visitor_key.strip() else default_key

if default_key and not visitor_key:
    st.sidebar.caption("Using the app's built-in API key.")
elif visitor_key:
    st.sidebar.caption("Using the key you entered (this session only).")
else:
    st.sidebar.caption("No API key available yet — enter one above to use the app.")


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
        if not effective_api_key:
            st.error("No API key available. Please enter one in the sidebar first.")
        else:
            status_box = st.empty()
            log_lines = []

            def report(msg):
                log_lines.append(msg)
                status_box.info("\n\n".join(log_lines[-5:]))

            with st.spinner("Processing PDF..."):
                try:
                    output_bytes, corrections, summary = process_pdf_bytes(
                        input_bytes, progress_callback=report, api_key=effective_api_key
                    )
                    st.session_state.output_bytes = output_bytes
                    st.session_state.corrections = corrections
                    st.session_state.summary = summary
                    status_box.success("Done!")
                except Exception as e:
                    status_box.error(f"Something went wrong: {e}")


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
