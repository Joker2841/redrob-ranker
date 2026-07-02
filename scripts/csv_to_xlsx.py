#!/usr/bin/env python3
import csv
import sys
import os
import zipfile
import xml.sax.saxutils as sax

def col_letter(n):
    # 1-based col to letters
    string = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        string = chr(65 + rem) + string
    return string

def build_sheet_xml(rows):
    sheet_head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    sheet_head += '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    sheet_head += ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
    sheet_head += '<sheetData>\n'
    body = []
    for r_idx, row in enumerate(rows, start=1):
        cols = []
        for c_idx, val in enumerate(row, start=1):
            cell_ref = f"{col_letter(c_idx)}{r_idx}"
            # Excel expects certain characters escaped; use inlineStr for safety
            text = sax.escape(str(val))
            cols.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        body.append(f'<row r="{r_idx}">' + "".join(cols) + '</row>')
    sheet_tail = '\n'.join(body) + '\n'
    sheet_tail += '</sheetData>\n</worksheet>'
    return sheet_head + sheet_tail

CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''

RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="/xl/workbook.xml"/>
</Relationships>'''

WORKBOOK = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>'''

WORKBOOK_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>'''

STYLES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><color theme="1"/><name val="Calibri"/></font></fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0"/></cellXfs>
</styleSheet>'''

def csv_to_xlsx(csv_path, xlsx_path):
    rows = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(row)
    sheet = build_sheet_xml(rows)

    with zipfile.ZipFile(xlsx_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', CONTENT_TYPES)
        z.writestr('_rels/.rels', RELS)
        z.writestr('xl/workbook.xml', WORKBOOK)
        z.writestr('xl/_rels/workbook.xml.rels', WORKBOOK_RELS)
        z.writestr('xl/worksheets/sheet1.xml', sheet)
        z.writestr('xl/styles.xml', STYLES)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        csv_p = sys.argv[1]
    else:
        csv_p = 'team_xxx.csv'
    if not os.path.exists(csv_p):
        print('CSV not found:', csv_p, file=sys.stderr)
        sys.exit(2)
    out = os.path.splitext(csv_p)[0] + '.xlsx'
    csv_to_xlsx(csv_p, out)
    print('Wrote', out)
