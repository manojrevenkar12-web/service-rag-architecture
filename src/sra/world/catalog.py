"""The equipment maker's truth: products, variants, documented values per firmware revision,
fault codes with remedies and spare parts, and stock per warehouse.

Only the lab reads this. The product sees rendered manuals and a parts API, as a technician would.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from sra.rng import Rng

# The repository (or, in a container, the directory holding config/ and reports/).
ROOT = Path(os.environ.get("SRA_ROOT", Path(__file__).resolve().parents[3]))


def load_world_config(path: Path | None = None) -> dict:
    return json.loads((path or ROOT / "config" / "world.json").read_text())


@dataclass(frozen=True)
class Attribute:
    key: str
    de: str
    en: str
    unit: str
    level: str  # "model" or "variant"
    decimals: int = 0


ATTRIBUTES = [
    Attribute("max_ambient", "Max. Umgebungstemperatur", "Max. ambient temperature", "°C", "model"),
    Attribute("ip_rating", "Schutzart", "Degree of protection", "", "model"),
    Attribute("terminal_torque", "Anzugsdrehmoment Netzklemmen", "Tightening torque, mains terminals", "Nm", "model", 1),
    Attribute("fan_interval", "Lüfter-Austauschintervall", "Fan replacement interval", "h", "model"),
    Attribute("ramp_up", "P1120 Hochlaufzeit (Werkseinstellung)", "P1120 ramp-up time (factory setting)", "s", "model", 1),
    Attribute("overload", "P0640 Stromgrenze (Werkseinstellung)", "P0640 current limit (factory setting)", "%", "model"),
    Attribute("rated_current", "Bemessungsstrom", "Rated current", "A", "variant", 1),
    Attribute("weight", "Gewicht", "Weight", "kg", "variant", 1),
    Attribute("fuse", "Vorsicherung", "Upstream fuse", "A", "variant"),
]
ATTR = {a.key: a for a in ATTRIBUTES}
REVISABLE = ["max_ambient", "fan_interval", "ramp_up", "overload", "terminal_torque"]
# Asked about by technicians but documented in no manual: the right answer is "not documented".
UNDOCUMENTED = [("noise_level", "der Schallpegel", "sound pressure level"), ("mtbf", "die MTBF", "MTBF"),
                ("altitude_derating", "die Leistungsreduzierung ab 1000 m Aufstellhöhe", "altitude derating above 1000 m")]


@dataclass
class Fact:
    id: str
    model: str
    variant: str | None  # e.g. "11 kW"
    revision: str  # "A" or "B"
    attribute: str
    value: float | str


@dataclass
class FaultCode:
    code: str
    cause_de: str
    cause_en: str
    remedy_de: str
    remedy_en: str
    part: str | None


@dataclass
class Model:
    name: str  # e.g. "VD-340"
    family: str
    family_de: str
    family_en: str
    variants: list[float]
    order_number: str = ""
    series: str = ""
    facts: list[Fact] = field(default_factory=list)
    faults: list[FaultCode] = field(default_factory=list)
    # Facts per revision: values documented in rev A and rev B manuals.

    def value(self, attribute: str, revision: str, variant: str | None = None) -> Fact | None:
        for f in self.facts:
            if f.attribute == attribute and f.revision == revision and f.variant == variant:
                return f
        return None


@dataclass
class Catalog:
    models: list[Model]
    series: dict[str, list[str]]  # series id -> model names covered by one manual
    english_only: set[str]  # series without a German manual
    parts: dict[str, tuple[str, str]]  # part number -> (description de, en)
    stock: dict[tuple[str, str], int]  # (part, warehouse) -> units
    warehouses: list[str]

    def model(self, name: str) -> Model:
        return next(m for m in self.models if m.name == name)


def variant_label(kw: float) -> str:
    return f"{kw:g} kW"


CAUSES = [
    ("Überstrom im Zwischenkreis", "DC link overcurrent", "Motorleitung auf Kurzschluss prüfen", "Check the motor cable for a short circuit"),
    ("Kühlkörper-Übertemperatur", "Heat sink overtemperature", "Lüftermodul tauschen", "Replace the fan module"),
    ("Unterspannung Netz", "Mains undervoltage", "Netzspannung und Vorsicherung prüfen", "Check the mains voltage and the upstream fuse"),
    ("Geberfehler", "Encoder fault", "Geberkabel tauschen", "Replace the encoder cable"),
    ("Erdschluss am Ausgang", "Output earth fault", "Isolationswiderstand der Motorwicklung messen", "Measure the insulation resistance of the motor winding"),
    ("Kommunikationsausfall Feldbus", "Fieldbus communication loss", "Feldbuskarte tauschen", "Replace the fieldbus card"),
    ("Bremswiderstand überlastet", "Braking resistor overloaded", "Bremswiderstand tauschen", "Replace the braking resistor"),
    ("Speicherfehler Parameter", "Parameter memory fault", "Steuereinheit tauschen", "Replace the control unit"),
    ("Phasenausfall Netz", "Mains phase loss", "Netzzuleitung und Klemmen prüfen", "Check the mains supply and terminals"),
    ("Öltemperatur zu hoch", "Oil temperature too high", "Ölfilter tauschen", "Replace the oil filter"),
    ("Kältemittel-Hochdruck", "Refrigerant high pressure", "Verflüssigerlüfter tauschen", "Replace the condenser fan"),
    ("Sicherheitskreis offen", "Safety circuit open", "Not-Halt-Kreis und Schutztür prüfen", "Check the emergency stop circuit and guard door"),
    ("Achsfehler Schleppabstand", "Axis following error", "Achsmotor und Getriebe prüfen", "Check the axis motor and gearbox"),
    ("Puffer-Batterie leer", "Backup battery empty", "Puffer-Batterie tauschen", "Replace the backup battery"),
    ("Lüfter blockiert", "Fan blocked", "Lüftermodul tauschen", "Replace the fan module"),
    ("Zwischenkreis-Überspannung", "DC link overvoltage", "Bremschopper tauschen", "Replace the brake chopper"),
]
PART_WORDS = {
    "Lüftermodul": "fan module", "Geberkabel": "encoder cable", "Feldbuskarte": "fieldbus card", "Bremswiderstand": "braking resistor",
    "Steuereinheit": "control unit", "Ölfilter": "oil filter", "Verflüssigerlüfter": "condenser fan", "Puffer-Batterie": "backup battery",
    "Bremschopper": "brake chopper",
}


def build_catalog(seed: int, cfg: dict) -> Catalog:
    rng = Rng(seed, "catalog")
    models: list[Model] = []
    parts: dict[str, tuple[str, str]] = {}
    used_names: set[str] = set()
    for fam in cfg["families"]:
        frng = rng.child(fam["key"])
        # Model numbers close to each other on purpose: VD-340 and VD-430 are both real.
        numbers = frng.sample(range(110, 990, 10), cfg["modelsPerFamily"])
        for k, num in enumerate(numbers):
            name = f"{fam['prefix']}-{num}"
            if name in used_names:
                continue
            used_names.add(name)
            r = frng.child(name)
            variants = list(fam["variantsKw"][k % len(fam["variantsKw"])])
            m = Model(name, fam["key"], fam["de"], fam["en"], variants,
                      order_number=f"6{fam['prefix']}{num:03d}{r.randint(0, 9)}-{r.randint(1, 9)}{r.choice('ABCDE')}{r.choice('ABCDE')}{r.randint(0, 9)}")
            base: dict[str, float | str] = {
                "max_ambient": r.choice([40, 45, 50]),
                "ip_rating": r.choice(["IP20", "IP21", "IP54", "IP55"]),
                "terminal_torque": r.choice([0.6, 0.8, 1.2, 1.5, 2.5, 4.0]),
                "fan_interval": r.choice([20000, 30000, 40000, 50000]),
                "ramp_up": r.choice([2.0, 5.0, 10.0, 15.0, 20.0]),
                "overload": r.choice([110, 120, 150, 160, 200]),
            }
            for rev in ("A", "B"):
                for key, v in base.items():
                    value: float | str = v
                    if rev == "B" and key in REVISABLE and r.random() < cfg["revisionChangeProbability"]:
                        value = _revised(key, v, r)
                        base[key] = value
                    m.facts.append(Fact(f"{name}/{rev}/{key}", name, None, rev, key, value))
                for kw in variants:
                    vl = variant_label(kw)
                    current = round(kw * 2.05 * (1 + 0.04 * r.random()), 1)
                    m.facts.append(Fact(f"{name}/{rev}/{vl}/rated_current", name, vl, rev, "rated_current", current))
                    m.facts.append(Fact(f"{name}/{rev}/{vl}/weight", name, vl, rev, "weight", round(2.5 + kw * 0.9 + r.random() * 2, 1)))
                    m.facts.append(Fact(f"{name}/{rev}/{vl}/fuse", name, vl, rev, "fuse", _fuse(current)))
            models.append(m)
        # Fault codes are shared within a family; remedies point to the family's parts.
        codes = frng.sample(range(1, 999), cfg["errorCodesPerFamily"])
        chosen = frng.sample(CAUSES, min(len(CAUSES), cfg["errorCodesPerFamily"]))
        for code_num, (cde, cen, rde, ren) in zip(codes, chosen, strict=False):
            code = f"F{code_num:04d}"
            part = None
            word = next((w for w in PART_WORDS if w in rde), None)
            if word and frng.random() < cfg["partShareOfErrorCodes"] + 0.3:
                part = f"{fam['prefix']}{frng.randint(1000, 9999)}-{frng.choice(['A', 'B', 'C'])}"
                parts[part] = (word, PART_WORDS[word])
            for m in models:
                if m.family == fam["key"]:
                    m.faults.append(FaultCode(code, cde, cen, rde, ren, part))
    stock_rng = Rng(seed, "stock")
    stock = {(p, w): stock_rng.choice([0, 0, 1, 2, 3, 5, 8, 12]) for p in parts for w in cfg["warehouses"]}
    # One manual covers a series of neighbouring models, as real manuals do.
    series: dict[str, list[str]] = {}
    srng = Rng(seed, "series")
    for fam in cfg["families"]:
        fam_models = sorted((m for m in models if m.family == fam["key"]), key=lambda m: m.name)
        i = 0
        while i < len(fam_models):
            size = srng.randint(*cfg["seriesSize"])
            group = fam_models[i:i + size]
            sid = f"{group[0].name}..{group[-1].name.split('-')[1]}" if len(group) > 1 else group[0].name
            for m in group:
                m.series = sid
            series[sid] = [m.name for m in group]
            i += size
    english_only = {sid for sid in series if srng.random() < cfg["englishOnlyShare"]}
    return Catalog(models, series, english_only, parts, stock, cfg["warehouses"])


def _revised(key: str, v: float | str, r: Rng) -> float | str:
    if key == "max_ambient":
        return v + 5 if isinstance(v, int | float) and v < 50 else 45
    if key == "fan_interval":
        return v + 10000 if isinstance(v, int | float) else v
    if key == "ramp_up":
        return r.choice([x for x in (2.0, 5.0, 10.0, 15.0, 20.0) if x != v])
    if key == "overload":
        return r.choice([x for x in (110, 120, 150, 160, 200) if x != v])
    return r.choice([x for x in (0.6, 0.8, 1.2, 1.5, 2.5, 4.0) if x != v])


def _fuse(current: float) -> int:
    for f in (6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200):
        if f >= current * 1.25:
            return f
    return 250
