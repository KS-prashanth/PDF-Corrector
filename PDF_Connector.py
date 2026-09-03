import sys
from PDF_core import process_pdf_bytes


def main():
    if len(sys.argv) != 3:
        print("Usage: python pdf_corrector.py <input.pdf> <output.pdf>")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    with open(input_path, "rb") as f:
        input_bytes = f.read()

    output_bytes, corrections, summary = process_pdf_bytes(
        input_bytes, progress_callback=print
    )

    with open(output_path, "wb") as f:
        f.write(output_bytes)

    print(f"\n{len(corrections)} correction(s) made.")
    print(f"Output saved to {output_path}")


if __name__ == "__main__":
    main()