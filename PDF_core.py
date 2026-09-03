
import json
import fitz  # PyMuPDF
from openai import OpenAI

MODEL = "gpt-4o-mini"  


def get_client(api_key=None):
    if api_key:
        return OpenAI(api_key=api_key)
    return OpenAI()


def extract_pages(doc):
  
    pages_data = []
    for page in doc:
        spans = []
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if "lines" not in b:
                continue
            for line in b["lines"]:
                for span in line["spans"]:
                    text = span["text"]
                    if not text.strip():
                        continue
                    spans.append({
                        "id": len(spans),
                        "text": text,
                        "bbox": span["bbox"],
                        "font": span["font"],
                        "size": span["size"],
                        "color": span["color"],
                    })
        pages_data.append(spans)
    return pages_data


def correct_page_spans(client, spans, max_retries=2, on_warning=None):
    if not spans:
        return spans

    payload = [{"id": s["id"], "text": s["text"]} for s in spans]

    prompt = f"""You will receive a JSON array of text fragments extracted from a PDF,
each with an "id" and "text". Fix ONLY spelling and grammar mistakes in each
fragment. Do not change meaning, do not merge or split fragments, and do not
add commentary. Return ONLY a JSON array of objects with "id" and "corrected"
keys, one per input fragment, same ids, no extra text before or after.

Input fragments:
{json.dumps(payload, ensure_ascii=False)}"""

    for attempt in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw
                if raw.endswith("json"):
                    raw = raw[:-4]

            corrected_list = json.loads(raw)
            corrected_map = {item["id"]: item["corrected"] for item in corrected_list}

            for s in spans:
                s["corrected"] = corrected_map.get(s["id"], s["text"])
            return spans

        except Exception as e:
            if attempt == max_retries:
                msg = f"correction failed after retries ({e}); leaving page text unchanged."
                if on_warning:
                    on_warning(msg)
                else:
                    print(f"  [warn] {msg}")
                for s in spans:
                    s["corrected"] = s["text"]
                return spans
            continue



def register_page_fonts(doc, page):

    font_map = {}
    for font in page.get_fonts(full=True):
        xref, ext, ftype, basefont, fontname, encoding = font[:6]
        try:
            extracted = doc.extract_font(xref)
            fontbuffer = extracted[3]
            if fontbuffer:
                page.insert_font(fontname=fontname, fontbuffer=fontbuffer)
                font_map[basefont] = fontname
        except Exception:
            continue
    return font_map


def fit_fontsize(text, fontname, max_size, max_width, min_size=6.0):
    """Shrink font size until text fits within max_width, or hit min_size."""
    size = max_size
    while size > min_size:
        try:
            width = fitz.get_text_length(text, fontname=fontname, fontsize=size)
        except Exception:
            width = fitz.get_text_length(text, fontname="helv", fontsize=size)
        if width <= max_width:
            return size
        size -= 0.5
    return min_size


def _int_to_rgb(color_int):
    r = (color_int >> 16) & 255
    g = (color_int >> 8) & 255
    b = color_int & 255
    return (r, g, b)


def rewrite_pdf(doc, pages_data, output_path):

    for page, spans in zip(doc, pages_data):
        font_map = register_page_fonts(doc, page)
        to_redact = [
            s for s in spans
            if s["text"].strip() != s["corrected"].strip()
        ]

        for s in to_redact:
            rect = fitz.Rect(s["bbox"])
            page.add_redact_annot(rect, fill=(1, 1, 1))

        if to_redact:
            page.apply_redactions()

        for s in to_redact:
            rect = fitz.Rect(s["bbox"])
            corrected = s["corrected"].strip()
            usable_font = font_map.get(s["font"], "helv")
            fitted_size = fit_fontsize(corrected, usable_font, s["size"], rect.width)

            try:
                page.insert_text(
                    (rect.x0, rect.y1 - 2),
                    corrected,
                    fontsize=fitted_size,
                    fontname=usable_font,
                    color=tuple(c / 255 for c in _int_to_rgb(s["color"])),
                )
            except Exception:
                page.insert_text(
                    (rect.x0, rect.y1 - 2),
                    corrected,
                    fontsize=fitted_size,
                    fontname="helv",
                )

    doc.save(output_path)


# ---------------------------------------------------------------------------
# Step 4: Summary
# ---------------------------------------------------------------------------

def generate_summary(client, full_text, on_error=None):
    prompt = f"""Summarize the following document in exactly 2 short paragraphs.
Be concise and capture the main points only.

Document:
{full_text[:12000]}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        if on_error:
            on_error(str(e))
        else:
            print(f"  [error] summary generation failed: {e}")
        return ("Summary unavailable: the summary could not be generated "
                "due to an API error. Please check your API key/quota and try again.")


def append_summary_page(doc, summary_text):
    page = doc.new_page()
    page.insert_text((50, 60), "Summary", fontsize=18, fontname="helv")
    page.insert_textbox(
        fitz.Rect(50, 90, page.rect.width - 50, page.rect.height - 50),
        summary_text,
        fontsize=11,
        fontname="helv",
    )


def get_corrections_list(pages_data):

    corrections = []
    for page_num, spans in enumerate(pages_data, 1):
        for s in spans:
            original = s["text"].strip()
            corrected = s["corrected"].strip()
            if original and original != corrected:
                corrections.append({
                    "page": page_num,
                    "original": original,
                    "corrected": corrected,
                })
    return corrections



def process_pdf_bytes(input_bytes, progress_callback=None):

    def report(msg):
        if progress_callback:
            progress_callback(msg)

    client = get_client()
    doc = fitz.open(stream=input_bytes, filetype="pdf")

    report("Extracting text...")
    pages_data = extract_pages(doc)

    report(f"Correcting {len(pages_data)} page(s)...")
    for i, spans in enumerate(pages_data, 1):
        report(f"Correcting page {i}/{len(pages_data)}...")
        correct_page_spans(client, spans, on_warning=report)

    corrections = get_corrections_list(pages_data)

    report("Rewriting PDF with corrections...")

    for page, spans in zip(doc, pages_data):
        font_map = register_page_fonts(doc, page)
        to_redact = [s for s in spans if s["text"].strip() != s["corrected"].strip()]

        for s in to_redact:
            rect = fitz.Rect(s["bbox"])
            page.add_redact_annot(rect, fill=(1, 1, 1))
        if to_redact:
            page.apply_redactions()

        for s in to_redact:
            rect = fitz.Rect(s["bbox"])
            corrected = s["corrected"].strip()
            usable_font = font_map.get(s["font"], "helv")
            fitted_size = fit_fontsize(corrected, usable_font, s["size"], rect.width)
            try:
                page.insert_text(
                    (rect.x0, rect.y1 - 2),
                    corrected,
                    fontsize=fitted_size,
                    fontname=usable_font,
                    color=tuple(c / 255 for c in _int_to_rgb(s["color"])),
                )
            except Exception:
                page.insert_text(
                    (rect.x0, rect.y1 - 2),
                    corrected,
                    fontsize=fitted_size,
                    fontname="helv",
                )

    full_text = " ".join(s["corrected"] for spans in pages_data for s in spans)

    report("Generating summary...")
    summary = generate_summary(client, full_text, on_error=report)

    report("Appending summary page...")
    try:
        append_summary_page(doc, summary)
    except Exception as e:
        report(f"could not append summary page: {e}")

    output_bytes = doc.tobytes()
    doc.close()

    report("Done.")
    return output_bytes, corrections, summary
