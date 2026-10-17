"""Search terms for the Phu Phan centre and its models.

Two kinds of terms, used differently on purpose:
- real alternative names people use (หมูภูพาน, ไก่หวายดำ, Puparn ...): shown to visitors as
  "ชื่อเรียกอื่น", in the meta description and in structured data (alternateName).
- common misspellings (พูพาน, ภูภาน, ศูญย์ ...): only in the keywords meta tag and the
  WebSite alternateName. Google already corrects most typos itself ("did you mean"), and
  repeating misspellings in visible text is treated as keyword stuffing, so they stay out of
  the page text.
Sources for the alternative names: news and the centre's own material on the "3 ดำ / 5 ดำ
มหัศจรรย์ภูพาน" (Matichon, Technology Chaoban, Thairath) and Museum Thailand (English names).
"""
from __future__ import annotations

import re

CENTRE_NAME = "ศูนย์ศึกษาการพัฒนาภูพานอันเนื่องมาจากพระราชดำริ"
CENTRE_ALT_NAMES = [
    "ศูนย์ศึกษาการพัฒนาภูพาน",
    "ศูนย์ภูพาน",
    "ศูนย์ฯ ภูพาน",
    "ศูนย์ศึกษาการพัฒนาภูพานฯ สกลนคร",
    "Phu Phan Royal Development Study Centre",
    "Puparn Royal Development Study Centre",
]
CENTRE_MISSPELLINGS = [
    "พูพาน", "ภูภาน", "พูภาน", "ภุพาน", "ภูพาณ", "ภูพาร",
    "ศูญย์ภูพาน", "ศูนภูพาน", "ศูนย์พูพาน", "ศูนย์ศึกษาพัฒนาภูพาน",
    "ศูนย์ศึกษาการพัฒนาพูพาน", "ศูญย์ศึกษาการพัฒนาภูพาน", "ศูนย์การศึกษาการพัฒนาภูพาน",
    "phuphan", "phu phan", "puparn", "phupan", "poopan",
]
GROUP_TERMS = ["3 ดำภูพาน", "3 ดำมหัศจรรย์ภูพาน", "5 ดำมหัศจรรย์ภูพาน", "สัตว์ดำภูพาน"]
SITE_TERMS = ["ภูพาน AR", "โมเดล 3D ภูพาน", "ของดีสกลนคร", "แหล่งเรียนรู้สกลนคร", "พิพิธภัณฑ์ออนไลน์สกลนคร"]

# Exact model name (cleaned) -> real alternative names.
MODEL_ALIASES = {
    "สุกรภูพาน": ["หมูภูพาน", "หมูดำภูพาน", "สุกรดำภูพาน", "หมูดำ"],
    "โคเนื้อภูพาน": ["วัวภูพาน", "วัวเนื้อภูพาน", "โคภูพาน", "โคเนื้อทาจิมะภูพาน", "วากิวภูพาน"],
    "กระต่ายดำ": ["กระต่ายดำภูพาน"],
    "กวางรูซ่า": ["กวางรูซ่าภูพาน", "กวางภูพาน"],
    "เป็ดบาบารี่": ["เป็ดบาบาลี", "เป็ดบาบารี"],
    "ชุดผ้าไหมย้อมคราม": ["ผ้าไหมย้อมคราม", "ผ้าย้อมคราม", "ผ้าครามสกลนคร"],
    "กระเป๋าผ้าไหมทรงกลม": ["กระเป๋าผ้าไหม"],
    "กระเป๋าผ้าไหมทรงสี่เหลี่ยม": ["กระเป๋าผ้าไหม"],
    "ตัวไหมพันธุ์นางสิ่ว": ["ตัวไหม", "หนอนไหม"],
    "ลูกหม่อน": ["หม่อน", "มัลเบอร์รี่"],
    "ต้นยางพารา": ["ยางพารา"],
    "ลูกประคบ": ["ลูกประคบสมุนไพร"],
    "ยาดม": ["ยาดมสมุนไพร"],
    "วุ้นเส้นถั่วเขียว": ["วุ้นเส้น"],
    "ธัญพืชอัดแท่ง": ["ธัญพืชแท่ง", "ขนมธัญพืชอัดแท่ง"],
    "เห็ดหลินจือ": ["เห็ดหลินจือแดง"],
    "ข้าวภูพาน 1": ["ข้าวพันธุ์ภูพาน 1"],
    "รวงข้าวสกลนคร": ["ข้าวสกลนคร"],
    "ปลานิลแดง": ["ปลานิลแดงภูพาน"],
}
CHICKEN = re.compile(r"ไก่ดำภูพาน\s*(\d)\s*/?\s*(.*)")


def clean_name(name: str) -> str:
    """'ไก่ดำภูพาน3 /สีน้ำตาล' -> 'ไก่ดำภูพาน 3 (สีน้ำตาล)'."""
    name = (name or "").strip()
    match = CHICKEN.fullmatch(name)
    if match:
        number, colour = match.group(1), match.group(2).strip()
        return f"ไก่ดำภูพาน {number}" + (f" ({colour})" if colour else "")
    return re.sub(r"\s+", " ", name)


def model_aliases(name: str) -> list[str]:
    """Real alternative names for a model (shown to visitors and in structured data)."""
    name = (name or "").strip()
    aliases: list[str] = []
    match = CHICKEN.fullmatch(name)
    if match:
        number, colour = match.group(1), match.group(2).strip()
        aliases += [f"ไก่ดำภูพาน {number}", f"ไก่ภูพาน {number}", "ไก่ดำภูพาน", "ไก่ดำ"]
        if colour:
            aliases.append(f"ไก่ดำภูพาน {colour}")
        if number == "4" or "หวาย" in colour:
            aliases[0:0] = ["ไก่หวายดำ", "ไก่หวายดำภูพาน 4"]
    aliases += MODEL_ALIASES.get(clean_name(name), [])
    return _unique([a for a in aliases if a and a != name and a != clean_name(name)])


def in_group(name: str) -> bool:
    """Part of the centre's famous black livestock (3 ดำ / 5 ดำมหัศจรรย์ภูพาน)."""
    return any(key in (name or "") for key in ("สุกรภูพาน", "โคเนื้อภูพาน", "ไก่ดำภูพาน", "กระต่ายดำ", "กวางรูซ่า"))


def model_keywords(name: str, project_name: str = "") -> list[str]:
    base = clean_name(name)
    words = [base, *model_aliases(name)]
    words += [f"{base} ภูพาน" if "ภูพาน" not in base else base, f"{base} สกลนคร"]
    if project_name:
        words.append(project_name)
    if in_group(name):
        words += GROUP_TERMS
    words += ["ศูนย์ศึกษาการพัฒนาภูพาน", "ศูนย์ภูพาน", "โมเดล 3D", "AR"]
    return _unique(words)


def site_keywords() -> list[str]:
    return _unique([CENTRE_NAME, *CENTRE_ALT_NAMES, *GROUP_TERMS, *SITE_TERMS, *CENTRE_MISSPELLINGS])


def _unique(items):
    seen, out = set(), []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out
