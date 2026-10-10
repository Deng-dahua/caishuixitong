import json, zipfile, re
# Minimal xlsx reader (no openpyxl dep) - parse sharedStrings + sheet xml
path = "data/uploads/1/1_928_2025年科目余额表.xlsx"
z = zipfile.ZipFile(path)
names = z.namelist()
# shared strings
shared = []
if "xl/sharedStrings.xml" in names:
    import xml.etree.ElementTree as ET
    t = ET.fromstring(z.read("xl/sharedStrings.xml"))
    for si in t:
        txt = "".join(node.text or "" for node in si.iter() if node.tag.endswith("}t")
                      and not node.tag.endswith("}r"))  # simplistic
        # better: collect all <t>
        pass
# simpler: just extract all text from sheet1
sheet = [n for n in names if n.startswith("xl/worksheets/sheet")][0]
xml = z.read(sheet).decode("utf-8", "ignore")
# extract cell values: shared strings referenced via t="s"
# get shared string list properly
if "xl/sharedStrings.xml" in names:
    ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
    shared = []
    for si in ss.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
        # concatenate all <t> under si
        s = "".join(tt.text or "" for tt in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
        shared.append(s)
# parse sheet cells
cells = re.findall(r'<c r="([A-Z]+\d+)"[^>]*>(.*?)</c>', xml)
rows = []
for ref, inner in cells:
    m = re.search(r't="s"[^>]*>(?:<v>)?([^<]+)', inner)
    if m and "t=\"s\"" in inner:
        val = shared[int(m.group(1))]
    else:
        vm = re.search(r'<v>([^<]*)</v>', inner)
        val = vm.group(1) if vm else ""
    rows.append((ref, val))
# build row->cells
from collections import defaultdict
grid = defaultdict(dict)
for ref, val in rows:
    col = re.match(r"([A-Z]+)", ref).group(1)
    rnum = re.match(r"[A-Z]+(\d+)", ref).group(1)
    grid[rnum][col] = val
print("total rows:", len(grid))
# find any cell containing 实收资本/资本公积/资金账簿
hits = []
for rnum, row in grid.items():
    line = " | ".join(f"{k}={v}" for k,v in row.items())
    if any(kw in line for kw in ["实收资本","资本公积","资金账簿","实收"]):
        hits.append((rnum, line))
print("rows mentioning 实收资本/资本公积/资金账簿:", len(hits))
for h in hits[:20]:
    print("  ", h[0], h[1][:160])

print("\n=== SAMPLE ROWS 1-12 ===")
for r in range(1, 13):
    rn = str(r)
    if rn in grid:
        print(f"  row{rn}:", grid[rn])
print("\n=== ALL unique col-A (first col) values (account names) ===")
accts = [grid[str(r)].get("A","") for r in range(1,len(grid)+1) if grid[str(r)].get("A")]
print("first 30 account-name cells:", accts[:30])
# search account names for 资本/实收/权益
cap = [a for a in accts if any(k in a for k in ["资本","实收","权益","公积"])]
print("account names with 资本/实收/权益/公积:", cap[:30])
