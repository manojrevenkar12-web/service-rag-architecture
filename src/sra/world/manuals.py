"""Renders the catalog into the manuals a technician would search: one per model, revision and
language, with sections, tables, fault codes, spare parts and a revision history.

Each line carries the ids of the facts it states. The ids are hidden from the product: chunkers see
text only, and the lab uses the ids to know which chunks hold the answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sra.world.catalog import ATTR, Catalog, Model, variant_label


@dataclass
class Line:
    text: str
    section: str
    kind: str  # title, heading, text, table_header, table_row, history
    facts: tuple[str, ...] = ()


@dataclass
class Document:
    id: str
    models: tuple[str, ...]
    family: str
    revision: str
    firmware: str
    lang: str
    title: str
    lines: list[Line] = field(default_factory=list)
    # The index metadata as the document management system holds it. Some documents were
    # uploaded without it (scans, renamed files): then models is empty and revision unknown.
    meta_models: tuple[str, ...] = ()
    meta_revision: str = "?"

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


def fmt(value: float | str, decimals: int, lang: str) -> str:
    if isinstance(value, str):
        return value
    s = f"{value:.{decimals}f}"
    return s.replace(".", ",") if lang == "de" else s


def fmt_with_unit(attr_key: str, value: float | str, lang: str) -> str:
    a = ATTR[attr_key]
    v = fmt(value, a.decimals, lang)
    return f"{v} {a.unit}".strip()


T = {
    "manual": {"de": "Betriebsanleitung", "en": "Operating instructions"},
    "edition": {"de": "Ausgabe", "en": "Edition"},
    "safety": {"de": "1 Sicherheitshinweise", "en": "1 Safety instructions"},
    "tech": {"de": "2 Technische Daten", "en": "2 Technical data"},
    "general": {"de": "2.1 Allgemeine Daten", "en": "2.1 General data"},
    "variants": {"de": "2.2 Leistungsvarianten", "en": "2.2 Power variants"},
    "install": {"de": "3 Installation", "en": "3 Installation"},
    "params": {"de": "4 Parameter", "en": "4 Parameters"},
    "maint": {"de": "5 Wartung", "en": "5 Maintenance"},
    "faults": {"de": "6 Störungsmeldungen", "en": "6 Fault codes"},
    "parts": {"de": "7 Ersatzteile", "en": "7 Spare parts"},
    "history": {"de": "8 Änderungshistorie", "en": "8 Revision history"},
    "variant": {"de": "Variante", "en": "Variant"},
    "part_no": {"de": "Teilenummer", "en": "Part number"},
    "desc": {"de": "Bezeichnung", "en": "Description"},
    "cause": {"de": "Ursache", "en": "Cause"},
    "remedy": {"de": "Abhilfe", "en": "Remedy"},
    "spare": {"de": "Ersatzteil", "en": "spare part"},
}

SAFETY = {
    "de": [
        "Arbeiten am Gerät nur durch Elektrofachkräfte. Vor allen Arbeiten das Gerät spannungsfrei schalten und 5 Minuten warten, bis der Zwischenkreis entladen ist.",
        "Die Sicherheitsfunktion STO (Safe Torque Off) darf nicht überbrückt oder umgangen werden. Schutztüren und Not-Halt-Kreise müssen immer wirksam sein.",
        "Bei Arbeiten an Kältemittel- oder Druckluftkreisen ist das System drucklos zu machen.",
    ],
    "en": [
        "Work on the unit must be carried out by qualified electricians only. Before any work, isolate the unit and wait 5 minutes for the DC link to discharge.",
        "The safety function STO (Safe Torque Off) must never be bridged or bypassed. Guard doors and emergency stop circuits must always be effective.",
        "Before working on refrigerant or compressed-air circuits, depressurise the system.",
    ],
}
INSTALL = {
    "de": [
        "Das Gerät senkrecht montieren. Mindestabstand oben und unten 100 mm, seitlich 50 mm.",
        "Netzzuleitung mit Kupferleitern ausführen. Schirm der Motorleitung beidseitig großflächig auflegen.",
        "Bei Umgebungstemperaturen über 40 °C ist eine Leistungsreduzierung von 2,5 % je Kelvin zu beachten, sofern in den technischen Daten nichts anderes angegeben ist.",
        "Nach der Montage die Erdung mit einem Querschnitt von mindestens 10 mm² prüfen.",
    ],
    "en": [
        "Mount the unit vertically. Minimum clearance 100 mm above and below, 50 mm at the sides.",
        "Use copper conductors for the mains supply. Connect the motor cable shield over a large area at both ends.",
        "At ambient temperatures above 40 °C, derate by 2.5 % per kelvin unless the technical data state otherwise.",
        "After mounting, check the earth connection with a cross-section of at least 10 mm².",
    ],
}


def render(catalog: Catalog, defect_share: float = 0.0, seed: int = 0) -> list[Document]:
    from sra.rng import Rng

    docs: list[Document] = []
    by_name = {m.name: m for m in catalog.models}
    for sid, names in catalog.series.items():
        models = [by_name[n] for n in names]
        for rev, fw in (("A", "3"), ("B", "4")):
            for lang in ("de", "en"):
                if lang == "de" and sid in catalog.english_only:
                    continue
                d = _render_series(sid, models, rev, fw, lang, catalog)
                if Rng(seed, "metadata", d.id).random() >= defect_share:
                    d.meta_models, d.meta_revision = d.models, d.revision
                docs.append(d)
    return docs


def _label(key: str, lang: str) -> str:
    return ATTR[key].de if lang == "de" else ATTR[key].en


def _render_series(sid: str, models: list[Model], rev: str, fw: str, lang: str, catalog: Catalog) -> Document:
    first = models[0]
    fam = first.family_de if lang == "de" else first.family_en
    names = ", ".join(m.name for m in models)
    title = f"{fam} {names} – {T['manual'][lang]}, {T['edition'][lang]} {rev} (Firmware {fw}.x)"
    d = Document(f"{sid}_{rev}_{lang}", tuple(m.name for m in models), first.family, rev, fw, lang, title)
    add = d.lines.append
    model_col = "Modell" if lang == "de" else "Model"
    add(Line(title, "", "title"))
    add(Line(T["safety"][lang], T["safety"][lang], "heading"))
    for p in SAFETY[lang]:
        add(Line(p, T["safety"][lang], "text"))
    add(Line(T["tech"][lang], T["tech"][lang], "heading"))
    sec = T["general"][lang]
    add(Line(sec, sec, "heading"))
    keys = ("max_ambient", "ip_rating", "terminal_torque")
    add(Line(" | ".join([model_col] + [_label(k, lang) for k in keys]), sec, "table_header"))
    for m in models:
        cells, ids = [m.name], []
        for k in keys:
            f = m.value(k, rev)
            assert f is not None
            cells.append(fmt_with_unit(k, f.value, lang))
            ids.append(f.id)
        add(Line(" | ".join(cells), sec, "table_row", tuple(ids)))
    sec = T["variants"][lang]
    add(Line(sec, sec, "heading"))
    vkeys = ("rated_current", "weight", "fuse")
    add(Line(" | ".join([model_col, T["variant"][lang]] + [_label(k, lang) for k in vkeys]), sec, "table_header"))
    for m in models:
        for kw in m.variants:
            vl = variant_label(kw)
            cells = [m.name, (f"{kw:g}".replace(".", ",") if lang == "de" else f"{kw:g}") + " kW"]
            ids = []
            for k in vkeys:
                f = m.value(k, rev, vl)
                assert f is not None
                cells.append(fmt_with_unit(k, f.value, lang))
                ids.append(f.id)
            add(Line(" | ".join(cells), sec, "table_row", tuple(ids)))
    sec = T["install"][lang]
    add(Line(sec, sec, "heading"))
    for p in INSTALL[lang]:
        add(Line(p, sec, "text"))
    sec = T["params"][lang]
    add(Line(sec, sec, "heading"))
    for m in models:
        for key, rng in (("ramp_up", "0–650 s"), ("overload", "10–400 %")):
            f = m.value(key, rev)
            assert f is not None
            bereich = "Bereich" if lang == "de" else "range"
            add(Line(f"{m.name} – {_label(key, lang)}: {fmt_with_unit(key, f.value, lang)} ({bereich} {rng})", sec, "text", (f.id,)))
    sec = T["maint"][lang]
    add(Line(sec, sec, "heading"))
    for m in models:
        f = m.value("fan_interval", rev)
        assert f is not None
        add(Line(f"{m.name} – {_label('fan_interval', lang)}: {fmt_with_unit('fan_interval', f.value, lang)}", sec, "text", (f.id,)))
    sec = T["faults"][lang]
    add(Line(sec, sec, "heading"))
    for fc in first.faults:
        cause = fc.cause_de if lang == "de" else fc.cause_en
        remedy = fc.remedy_de if lang == "de" else fc.remedy_en
        part = f" ({'Ersatzteil' if lang == 'de' else 'Spare part'} {fc.part})" if fc.part else ""
        fids = tuple(f"{m.name}/{rev}/fault/{fc.code}" for m in models)
        add(Line(f"{fc.code} – {T['cause'][lang]}: {cause}. {T['remedy'][lang]}: {remedy}{part}.", sec, "text", fids))
    sec = T["parts"][lang]
    add(Line(sec, sec, "heading"))
    add(Line(f"{T['part_no'][lang]} | {T['desc'][lang]}", sec, "table_header"))
    for part in sorted({fc.part for fc in first.faults if fc.part}):
        de, en = catalog.parts[part]
        add(Line(f"{part} | {de if lang == 'de' else en}", sec, "table_row", (f"part/{part}",)))
    if rev == "B":
        sec = T["history"][lang]
        add(Line(sec, sec, "heading"))
        changed = False
        for m in models:
            for key in ("max_ambient", "fan_interval", "ramp_up", "overload", "terminal_torque"):
                a = m.value(key, "A")
                b = m.value(key, "B")
                if a and b and a.value != b.value:
                    changed = True
                    old, new = fmt_with_unit(key, a.value, lang), fmt_with_unit(key, b.value, lang)
                    text = (f"{T['edition'][lang]} B: {m.name} {_label(key, lang)} von {old} auf {new} geändert." if lang == "de"
                            else f"Edition B: {m.name} {_label(key, lang)} changed from {old} to {new}.")
                    add(Line(text, sec, "history", (f"history/{a.id}",)))
        if not changed:
            add(Line("Ausgabe B: redaktionelle Überarbeitung." if lang == "de" else "Edition B: editorial revision.", sec, "history"))
    return d
