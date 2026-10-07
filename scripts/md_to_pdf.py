"""Render samples/src/*.md to samples/*.pdf and write samples/MANIFEST.md (task D4).

Run from the repo root: uv run python scripts/md_to_pdf.py

Files with `scanned: true` in their front matter are rasterised at 150 dpi and rebuilt as an
image-only PDF, so they have no text layer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import fitz  # PyMuPDF
import fpdf
from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "samples" / "src"
OUT = ROOT / "samples"

# One fact per document that a retrieval test question could target.
KEY_FACTS = {
    "01": "Car mileage claim rate is RM0.60 per km under Pekeliling Kewangan Bil. 2/2022.",
    "02": "Car mileage claim rate rises from RM0.60 to RM0.70 per km, effective 1 Februari 2024.",
    "03": "Direct purchase limit is RM20,000; above that, three written quotations (Form PRO-03).",
    "04": "Direct purchase limit raised from RM20,000 to RM50,000, effective 1 June 2023.",
    "05": "Flexi hours core time is 10.00 pagi to 3.00 petang; apply with Borang SM-07.",
    "06": "Purchases above RM200,000 up to RM500,000 are finally approved by the Chief Finance Officer.",
    "07": "Level 3 incidents must be reported to the Pusat Keselamatan Siber Negeri within 24 jam.",
    "08": "Vehicle bookings must be made at least 3 hari bekerja before travel via e-Booking Kenderaan.",
    "09": "All staff must complete Cyber Hygiene Essentials by 30 June 2024 or lose e-Procurement and HRMS access.",
    "10": "Committee approved RM1.2 juta of the RM1.45 juta extra funding requested for Portal Digital Rakyat.",
    "11": "Training plan 2024 approved with RM480,000; study leave bond is 3 tahun (Borang SM-15).",
    "12": "Passwords must be at least 12 aksara and changed every 90 hari; accounts lock after 5 failed logins.",
    "13": "Annual leave entitlement is 20 days a year under 10 years of service, 25 days from 10 years.",
    "14": "Financial and procurement records are retained for 7 tahun; scans must be 300 dpi PDF/A.",
    "15": "Token gifts are capped at RM100 and gifts of RM50 or more must be declared on Form ADM-06.",
}

UNICODE_FALLBACKS = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    "…": "...",
    " ": " ",
}


def find_dejavu() -> Path | None:
    """Return a DejaVuSans.ttf bundled inside the installed fpdf2 package, if any."""
    pkg = Path(fpdf.__file__).parent
    for p in pkg.rglob("DejaVuSans.ttf"):
        return p
    return None


def parse_front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("missing front matter")
    meta: dict = {}
    for line in m.group(1).splitlines():
        key, _, val = line.partition(":")
        val = val.strip()
        if val.startswith("["):
            meta[key.strip()] = json.loads(val)
        elif val in ("true", "false"):
            meta[key.strip()] = val == "true"
        elif val.isdigit():
            meta[key.strip()] = int(val)
        else:
            meta[key.strip()] = val
    return meta, text[m.end():]


class Renderer:
    def __init__(self) -> None:
        self.pdf = FPDF(format="A4", unit="pt")
        self.pdf.set_margins(50, 50, 50)
        self.pdf.set_auto_page_break(True, margin=50)
        dejavu = find_dejavu()
        if dejavu:
            self.pdf.add_font("DejaVu", "", str(dejavu))
            bold = dejavu.with_name("DejaVuSans-Bold.ttf")
            self.pdf.add_font("DejaVu", "B", str(bold if bold.exists() else dejavu))
            self.family = "DejaVu"
            self.latin1 = False
        else:
            self.family = "Helvetica"
            self.latin1 = True
        self.pdf.add_page()

    def clean(self, s: str) -> str:
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = s.replace("`", "")
        if self.latin1:
            for k, v in UNICODE_FALLBACKS.items():
                s = s.replace(k, v)
            s = s.encode("latin-1", "replace").decode("latin-1")
        return s

    def line(self, text: str, *, size: float, bold: bool = False, indent: float = 0,
             family: str | None = None) -> None:
        self.pdf.set_font(family or self.family, "B" if bold else "", size)
        self.pdf.set_x(self.pdf.l_margin + indent)
        width = self.pdf.w - self.pdf.r_margin - self.pdf.get_x()
        self.pdf.multi_cell(width, size * 1.35, self.clean(text) if family != "Courier" else text,
                            new_x="LMARGIN", new_y="NEXT")

    def gap(self, pts: float = 6) -> None:
        self.pdf.ln(pts)

    def table(self, rows: list[list[str]]) -> None:
        rows = [[self.clean(c) for c in r] for r in rows]
        ncols = max(len(r) for r in rows)
        widths = [max(len(r[i]) if i < len(r) else 0 for r in rows) for i in range(ncols)]
        for idx, r in enumerate(rows):
            cells = [(r[i] if i < len(r) else "").ljust(widths[i]) for i in range(ncols)]
            self.line(" | ".join(cells), size=9, family="Courier")
            if idx == 0:
                self.line("-+-".join("-" * w for w in widths), size=9, family="Courier")
        self.gap(6)

    def render(self, body: str) -> None:
        table: list[list[str]] = []
        prev_blank = True
        for raw in body.splitlines():
            line = raw.rstrip()
            if line.lstrip().startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    table.append(cells)
                continue
            if table:
                self.table(table)
                table = []
            if not line.strip():
                if not prev_blank:
                    self.gap(6)
                prev_blank = True
                continue
            prev_blank = False
            if line.startswith("# "):
                self.line(line[2:], size=14, bold=True)
            elif line.startswith("## "):
                self.line(line[3:], size=12, bold=True)
            elif line.startswith("### "):
                self.line(line[4:], size=11, bold=True)
            elif re.match(r"^\s*(-|\*|[a-z]\.)\s+", line):
                self.line(line.strip(), size=11, indent=18)
            else:
                self.line(line, size=11)
        if table:
            self.table(table)

    def to_bytes(self) -> bytes:
        return bytes(self.pdf.output())


def rasterise(pdf_bytes: bytes) -> bytes:
    """Rebuild a PDF from 150 dpi page images only (no text layer)."""
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()
    for page in src:
        pix = page.get_pixmap(dpi=150)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=pix.tobytes("png"))
    data = out.tobytes(deflate=True)
    src.close()
    out.close()
    return data


def main() -> None:
    manifest: list[str] = []
    files = sorted(SRC.glob("*.md"))
    for md in files:
        meta, body = parse_front_matter(md.read_text(encoding="utf-8"))
        r = Renderer()
        r.render(body)
        data = r.to_bytes()
        if meta.get("scanned"):
            data = rasterise(data)
        (OUT / f"{md.stem}.pdf").write_bytes(data)
        nn = md.name[:2]
        manifest.append(
            f"- {md.stem}.pdf | doc_type: {meta['doc_type']} | department: {meta['department']}"
            f" | lang: {meta['lang']} | year: {meta['year']}"
            f" | supersedes: {json.dumps(meta['supersedes'], ensure_ascii=False)}"
            f" | scanned: {str(meta['scanned']).lower()} | key_fact: {KEY_FACTS[nn]}"
        )
        print(f"wrote {md.stem}.pdf" + (" (scanned)" if meta.get("scanned") else ""))
    header = (
        "# Seed corpus manifest\n\n"
        "Synthetic documents only. One line per PDF in `samples/`.\n\n"
    )
    (OUT / "MANIFEST.md").write_text(header + "\n".join(manifest) + "\n", encoding="utf-8")
    font = "DejaVuSans" if find_dejavu() else "Helvetica (latin-1)"
    print(f"{len(files)} PDFs, font: {font}")


if __name__ == "__main__":
    main()
