#!/usr/bin/env python3
"""Print a .docx as plain text, so git can diff the contract in readable form.

Wired up as a textconv driver (see README, "Reviewing template changes"), this
turns `git diff template/atp-website.docx` from "binary files differ" into the
actual clause wording that changed.

    python3 build/docxtext.py template/atp-website.docx
"""
import sys
from docx import Document
from docx.oxml.ns import qn


def cell_text(cell):
    return " / ".join(p.text.strip() for p in cell.paragraphs if p.text.strip())


def main(path):
    d = Document(path)

    for section in d.sections:
        for label, part in (("HEADER", section.header), ("FOOTER", section.footer)):
            for p in part.paragraphs:
                if p.text.strip():
                    print(f"[{label}] {p.text.strip()}")

    body = d.element.body
    t_index = 0
    for el in body:
        if el.tag == qn("w:p"):
            # read w:t nodes directly: python-docx defines .text at several levels,
            # so lxml's itertext() would repeat the same string
            txt = "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()
            if txt:
                print(txt)
        elif el.tag == qn("w:tbl"):
            table = d.tables[t_index]
            t_index += 1
            print(f"[TABLE {t_index}]")
            for row in table.rows:
                print("  | " + " | ".join(cell_text(c) for c in row.cells))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: docxtext.py <file.docx>")
    try:
        main(sys.argv[1])
    except Exception as e:                      # never break a git diff
        print(f"[could not read {sys.argv[1]}: {e}]")
