"""Run the parts of the skill's finalize that apply to a report without chapters/TOC:
condense letter-stretched Thai lines, then export a font-embedded PDF via Word."""
import os, sys
sys.path.insert(0, os.path.expanduser(r"~\.claude\skills\snru-thesis-docx\scripts"))
import finalize_thesis as ft
here = os.path.dirname(os.path.abspath(__file__))
docx_path, pdf_path = os.path.join(here, "report.docx"), os.path.join(here, "report.pdf")
ft.fix_stretched(docx_path)
ft.export_pdf(docx_path, pdf_path)
print("pdf", pdf_path)
