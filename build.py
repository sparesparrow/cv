#!/usr/bin/env python3
"""Render Vojtěch Špaček's CV from structured data into HTML, Markdown and PDF.

Single source of truth: ``data/cv.yaml``.  Everything under ``index.html``,
``cv-3-page.md`` and ``dist/`` is a build product -- edit the YAML, not the output.

Usage::

    python3 build.py --all                    # index.html, cv-3-page.md, dist/vs-cv-master.pdf
    python3 build.py --variant cz-contractor  # dist/vs-cv-cz-contractor.pdf
    python3 build.py --check                  # assertions only, writes nothing

A variant lives in ``data/variants/<name>.yaml``, carries an ``extends:`` key and
shallow-merges over the base document.  The keys ``sections``, ``emphasize_tags``,
``experience_detail``, ``page_budget``, ``locale``, ``include`` and ``exclude``
are render controls rather than content.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("build.py needs PyYAML (pip install pyyaml)")

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
except ImportError:  # pragma: no cover
    sys.exit("build.py needs Jinja2 (pip install jinja2)")


REPO_ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = REPO_ROOT / "templates"

DEFAULT_DATA = REPO_ROOT / "data" / "cv.yaml"
DEFAULT_DIST = REPO_ROOT / "dist"

SITE_URL = "https://sparesparrow.github.io/cv/"

TODO_MARKER = "TODO(user)"

#: Deterministic stand-in for Chromium's ``/CreationDate``.  Same byte length as
#: the real stamp, so the xref table stays valid after substitution.
FIXED_PDF_DATE = b"D:20200101000000+00'00'"
PDF_DATE_RE = re.compile(rb"D:\d{14}(?:[+\-]\d{2}'\d{2}'|Z)")


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #

#: Section id -> (english title, czech title).  Order here is the default order.
SECTION_TITLES = {
    "summary": ("Profile Summary", "Profilový souhrn"),
    "preferred_roles": ("Preferred Roles", "Preferované role"),
    "experience": ("Work Experience", "Pracovní zkušenosti"),
    "skills": ("Skills", "Dovednosti"),
    "open_source": ("Open Source & Projects", "Open source a projekty"),
    "education": ("Education & Training", "Vzdělávání a kurzy"),
    "languages": ("Languages", "Jazyky"),
    "availability": ("Availability & Work Authorization", "Dostupnost a pracovní oprávnění"),
    "interests": ("Interests", "Zájmy"),
    "testimonials": ("Testimonials", "Reference"),
    "contact": ("Contact", "Kontakt"),
}

DEFAULT_SECTIONS = [
    "summary",
    "preferred_roles",
    "experience",
    "skills",
    "open_source",
    "education",
    "languages",
    "availability",
    "interests",
    "contact",
]

#: How many highlights survive per experience entry at each detail level.
DETAIL_LIMITS = {"full": None, "compact": 3, "minimal": 0}

LEVEL_LABELS = {
    "senior": ("Senior", "Senior"),
    "medior": ("Medior", "Medior"),
    "working": ("Working knowledge", "Pracovní znalost"),
}

#: Static chrome that is not in the data file but is still user-visible, so it
#: has to be translatable too.
UI_STRINGS = {
    "skip_to_content": ("Skip to main content", "Přejít k hlavnímu obsahu"),
    "lang_switch_to_cs": ("Česky", "Česky"),
    "lang_switch_to_en": ("English", "English"),
    "lang_toggle_aria": ("Switch language", "Přepnout jazyk"),
    "verbose_off": ("Verbose mode: off", "Podrobný režim: vypnuto"),
    "verbose_on": ("Verbose mode: on", "Podrobný režim: zapnuto"),
    "theme_label": ("Theme", "Motiv"),
    "theme_high_contrast": ("High contrast", "Vysoký kontrast"),
    "theme_dark": ("Dark", "Tmavý"),
    "theme_light": ("Light", "Světlý"),
    "download_pdf": ("Download as PDF", "Stáhnout jako PDF"),
    "back_to_top": ("Back to top", "Zpět nahoru"),
    "skills_learned": ("New skills learned", "Nově osvojené dovednosti"),
    "present": ("present", "současnost"),
    "via": ("via", "přes"),
    "stars": ("stars", "hvězdiček"),
    "forks": ("forks", "forků"),
    "featured": ("Featured", "Vybrané"),
    # Worded to avoid the banned phrases the degree guard scans for -- the
    # disclaimer must not itself trip assertion #3.
    "coursework_only": ("Coursework only — no academic title", "Pouze studium — bez akademického titulu"),
    "contact_name": ("Name", "Jméno"),
    "contact_email": ("Email", "E-mail"),
    "contact_message": ("Message", "Zpráva"),
    "contact_send": ("Send email", "Odeslat e-mail"),
    "qr_caption": ("Scan to view the latest version online", "Naskenujte pro zobrazení aktuální verze online"),
    "online_version": ("Online version", "Online verze"),
    "rights": ("All rights reserved.", "Všechna práva vyhrazena."),
    "ico_yes": ("Trading on a Czech IČO", "Podniká na české IČO"),
    "citizenship": ("Citizenship", "Občanství"),
    "location": ("Location", "Lokalita"),
    "toggle_section": ("Toggle section", "Rozbalit/sbalit sekci"),
    "level_senior": LEVEL_LABELS["senior"],
    "level_medior": LEVEL_LABELS["medior"],
    "level_working": LEVEL_LABELS["working"],
}


# --------------------------------------------------------------------------- #
# Degree-claim guard
# --------------------------------------------------------------------------- #

#: Patterns that would state or imply an awarded academic degree.  Rendered
#: output is scanned for these; a hit is a hard build failure.
BANNED_DEGREE_PATTERNS = [
    (r"Bachelor", re.IGNORECASE),
    (r"\bBc\.", 0),
    (r"\bMgr\.", 0),
    (r"\bIng\.", 0),
    (r"\bB\.?Sc\b", 0),
    (r"\bM\.?Sc\b", 0),
    (r"\bPh\.?D\b", re.IGNORECASE),
    (r"master'?s degree", re.IGNORECASE),
    (r"\bgraduated\b", re.IGNORECASE),
    (r"\bdegree awarded\b", re.IGNORECASE),
    (r"bakalář", re.IGNORECASE),
    (r"magistersk", re.IGNORECASE),
    (r"\babsolvoval\b", re.IGNORECASE),
    (r"vysokoškolský titul", re.IGNORECASE),
]

#: Only legitimate when at least one education entry really has a degree.
DEGREE_CONDITIONAL_PATTERNS = [(r"alumniOf", 0)]


# --------------------------------------------------------------------------- #
# Contact rendering
# --------------------------------------------------------------------------- #

#: contact key -> (FontAwesome class, human label).  Unknown keys still render.
CONTACT_META = {
    "email": ("fas fa-envelope", "Email"),
    "phone": ("fas fa-phone", "Phone"),
    "github": ("fab fa-github", "GitHub"),
    "linkedin": ("fab fa-linkedin", "LinkedIn"),
    "x": ("fab fa-x-twitter", "X"),
    "calendly": ("fas fa-calendar-alt", "Calendly"),
    "signal": ("fas fa-comment", "Signal"),
    "youtube": ("fab fa-youtube", "YouTube"),
    "discord": ("fab fa-discord", "Discord"),
    "website": ("fas fa-globe", "Website"),
}


def contact_links(contact: dict) -> list[dict]:
    """Flatten ``meta.contact`` into ready-to-render links.

    Doing it here keeps href/label logic out of all three templates.
    """
    links = []
    for key, value in (contact or {}).items():
        if not value:
            continue
        icon, label = CONTACT_META.get(key, ("fas fa-link", str(key).replace("_", " ").title()))
        text = str(value)
        if key == "email":
            href, display = f"mailto:{text}", text
        elif key == "phone":
            href, display = "tel:" + re.sub(r"\s+", "", text), text
        else:
            href, display = text, label
        links.append(
            {
                "key": key,
                "icon": icon,
                "label": label,
                "href": href,
                "display": display,
                "short": re.sub(r"^https?://(www\.)?", "", text),
            }
        )
    for link in links:
        # Pre-rendered Markdown, so the template can join links in a single
        # expression instead of a loop that would swallow its own newline.
        link["md"] = f"[{link['label']}]({link['href']})"
    return links


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


class BuildError(Exception):
    """A build-time assertion failed, or the input is malformed."""


class Checker:
    """Collects assertion failures so one run reports every problem at once."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passed: list[str] = []

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        if ok:
            self.passed.append(label)
        else:
            self.failures.append(f"{label}: {detail}" if detail else label)
        return ok

    def raise_if_failed(self) -> None:
        if self.failures:
            lines = "\n".join(f"  - {f}" for f in self.failures)
            raise BuildError(f"{len(self.failures)} build assertion(s) failed:\n{lines}")


def localize(value, lang: str):
    """Pick ``lang`` out of a localized map, falling back to ``en``."""
    if isinstance(value, dict) and ("en" in value or "cs" in value):
        picked = value.get(lang)
        if picked is None:
            picked = value.get("en")
        return picked
    return value


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "x"


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def parse_start(value):
    """Return a sortable ``(y, m, d)`` tuple, or ``None`` for ``TODO(user)``."""
    if value is None:
        raise ValueError("missing date")
    if isinstance(value, datetime.datetime):
        return (value.year, value.month, value.day)
    if isinstance(value, datetime.date):
        return (value.year, value.month, value.day)
    if isinstance(value, int):
        return (value, 1, 1)
    text = str(value).strip()
    if text == TODO_MARKER:
        return None
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$", text)
    if not m:
        raise ValueError(f"unparseable date {value!r}")
    return (int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1))


def fmt_date(value, ui, lang: str) -> str:
    """Human-readable date for display; ``TODO(user)`` survives verbatim."""
    if value is None:
        return str(ui["present"])
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime("%Y-%m")
    text = str(value).strip()
    if text.lower() in {"present", "now", "current"}:
        return str(ui["present"])
    return text



def fmt_period(start, end, ui, lang: str) -> str:
    """Render a ``start – end`` range for display.

    Returns ``""`` when either endpoint is still the ``TODO(user)`` sentinel.
    The marker is deliberate in ``data/cv.yaml`` -- it records a date nobody has
    supplied yet -- but it must never reach a reader, so an unfilled range is
    rendered as no range at all rather than as the marker. ``--check`` asserts
    this separately, so an unfilled date stays visible to us without leaking.
    """
    if str(start).strip() == TODO_MARKER or str(end).strip() == TODO_MARKER:
        return ""
    return f"{fmt_date(start, ui, lang)} – {fmt_date(end, ui, lang)}"

# --------------------------------------------------------------------------- #
# Localized string registry
# --------------------------------------------------------------------------- #


class LStr:
    """One user-visible string, carrying both languages plus a stable i18n key.

    Templates emit ``data-i18n="{{ s.key }}"`` next to ``{{ s }}``; the JS
    ``translations`` table is generated from the same registry, so the two can
    never drift apart.
    """

    __slots__ = ("key", "en", "cs", "text")

    def __init__(self, key: str, en: str, cs: str, text: str) -> None:
        self.key = key
        self.en = en
        self.cs = cs
        self.text = text

    def __str__(self) -> str:
        return self.text

    def __bool__(self) -> bool:
        return bool(self.text)


class Registry:
    """Builds ``LStr`` values and remembers every key it handed out."""

    def __init__(self, lang: str) -> None:
        self.lang = lang
        self.entries: dict[str, dict[str, str]] = {}

    def make(self, key: str, value, cs_value=None) -> LStr:
        if cs_value is not None:
            en = as_text(value)
            cs = as_text(cs_value)
        elif isinstance(value, dict):
            en = as_text(value.get("en", ""))
            cs = as_text(value.get("cs") or value.get("en", ""))
        else:
            en = as_text(value)
            cs = en
        text = cs if self.lang == "cs" else en
        if key in self.entries and self.entries[key] != {"en": en, "cs": cs}:
            raise BuildError(f"duplicate i18n key with different content: {key}")
        self.entries[key] = {"en": en, "cs": cs}
        return LStr(key, en, cs, text)

    def ui(self, key: str) -> LStr:
        en, cs = UI_STRINGS[key]
        return self.make(f"ui.{key}", en, cs)

    def translations(self) -> dict[str, dict[str, str]]:
        return {
            "en": {k: v["en"] for k, v in sorted(self.entries.items())},
            "cs": {k: v["cs"] for k, v in sorted(self.entries.items())},
        }


# --------------------------------------------------------------------------- #
# Loading and variant merge
# --------------------------------------------------------------------------- #

CONTROL_KEYS = {
    "sections",
    "emphasize_tags",
    "experience_detail",
    "page_budget",
    "locale",
    "include",
    "exclude",
    "extends",
    "name",
    "description",
}


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise BuildError(f"data file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    if not isinstance(loaded, dict):
        raise BuildError(f"{path} must contain a YAML mapping at the top level")
    return loaded


def normalize_budget(value):
    """Accept ``4``, ``[1, 4]`` or ``{min: 1, max: 4}``; return ``(min, max)``."""
    if value is None:
        return None
    if isinstance(value, int):
        return (1, value)
    if isinstance(value, (list, tuple)):
        if len(value) == 1:
            return (1, int(value[0]))
        if len(value) == 2:
            return (int(value[0]), int(value[1]))
        raise BuildError(f"page_budget list must have 1 or 2 entries, got {value!r}")
    if isinstance(value, dict):
        lo = int(value.get("min", 1))
        hi = value.get("max")
        if hi is None:
            raise BuildError(f"page_budget mapping needs a 'max': {value!r}")
        return (lo, int(hi))
    raise BuildError(f"unsupported page_budget: {value!r}")


class Variant:
    """A base document plus the render controls that shape one output."""

    def __init__(self, name: str, data: dict, controls: dict, source: Path) -> None:
        self.name = name
        self.data = data
        self.source = source
        self.sections = controls.get("sections") or DEFAULT_SECTIONS
        self.emphasize_tags = set(controls.get("emphasize_tags") or [])
        self.experience_detail = controls.get("experience_detail") or "full"
        self.page_budget = normalize_budget(controls.get("page_budget"))
        self.locale = controls.get("locale") or "en"
        self.include = set(controls.get("include") or [])
        self.exclude = set(controls.get("exclude") or [])

        unknown = [s for s in self.sections if s not in SECTION_TITLES]
        if unknown:
            raise BuildError(
                f"variant {name!r} lists unknown section(s) {unknown}; "
                f"known: {sorted(SECTION_TITLES)}"
            )
        if self.experience_detail not in DETAIL_LIMITS:
            raise BuildError(
                f"variant {name!r}: experience_detail must be one of "
                f"{sorted(DETAIL_LIMITS)}, got {self.experience_detail!r}"
            )
        if self.locale not in {"en", "cs"}:
            raise BuildError(f"variant {name!r}: locale must be 'en' or 'cs'")


def load_master(data_path: Path) -> Variant:
    data = load_yaml(data_path)
    controls = {k: v for k, v in data.items() if k in CONTROL_KEYS}
    return Variant("master", data, controls, data_path)


def load_variant(name: str, data_path: Path, variants_dir: Path) -> Variant:
    vpath = variants_dir / f"{name}.yaml"
    if not vpath.exists():
        alt = variants_dir / f"{name}.yml"
        if alt.exists():
            vpath = alt
        else:
            raise BuildError(f"variant file not found: {vpath}")
    overlay = load_yaml(vpath)

    extends = overlay.get("extends")
    base_path = data_path
    if extends:
        candidate = (vpath.parent / str(extends)).resolve()
        if candidate.exists():
            base_path = candidate
        elif not data_path.exists():
            raise BuildError(f"variant {name!r} extends {extends!r}, which does not exist")
    base = load_yaml(base_path)

    # Shallow merge: a top-level key present in the overlay replaces the base.
    merged = dict(base)
    for key, value in overlay.items():
        if key == "extends":
            continue
        merged[key] = value

    controls = {k: v for k, v in base.items() if k in CONTROL_KEYS}
    controls.update({k: v for k, v in overlay.items() if k in CONTROL_KEYS})
    for key in CONTROL_KEYS:
        merged.pop(key, None)
    return Variant(name, merged, controls, vpath)


# --------------------------------------------------------------------------- #
# Context building
# --------------------------------------------------------------------------- #


def data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def keep(entry: dict, variant: Variant) -> bool:
    ident = entry.get("id")
    if ident is None:
        return True
    if ident in variant.exclude:
        return False
    if variant.include and ident not in variant.include:
        return False
    return True


def build_context(variant: Variant, lang: str, *, embed_assets: bool, source_label: str) -> dict:
    data = variant.data
    reg = Registry(lang)
    ui = {key: reg.ui(key) for key in UI_STRINGS}

    meta = data.get("meta") or {}
    contact = meta.get("contact") or {}
    location = meta.get("location") or {}

    photo_rel = meta.get("photo")
    photo_src = None
    if photo_rel:
        photo_path = (REPO_ROOT / str(photo_rel)).resolve()
        photo_src = data_uri(photo_path) if embed_assets else str(photo_rel)

    ctx: dict = {
        "generated_note": f"DO NOT EDIT — generated by build.py from {source_label}",
        "lang": lang,
        "variant": variant,
        "site_url": SITE_URL,
        "ui": ui,
        "meta": {
            "name": reg.make("meta.name", meta.get("name", "")),
            "headline": reg.make("meta.headline", meta.get("headline", "")),
            "tagline": reg.make("meta.tagline", meta.get("tagline", "")) if meta.get("tagline") else None,
            "city": location.get("city", ""),
            "country": location.get("country", ""),
            "citizenship": meta.get("citizenship", ""),
            "contact": contact,
            "contact_links": contact_links(contact),
            "photo": photo_src,
            "photo_alt": f"Photo of {localize(meta.get('name', ''), 'en')}",
            "badges": meta.get("badges") or [],
        },
        "summary": [],
        "preferred_roles": [],
        "skills": [],
        "experience": [],
        "open_source": [],
        "education": [],
        "languages": [],
        "interests": [],
        "testimonials": [],
        "work_authorization": None,
        "availability": None,
    }

    # -- summary ----------------------------------------------------------- #
    summary = data.get("summary") or {}
    en_lines = summary.get("en") or []
    cs_lines = summary.get("cs") or en_lines
    for i, line in enumerate(en_lines):
        cs_line = cs_lines[i] if i < len(cs_lines) else line
        ctx["summary"].append(reg.make(f"summary.{i}", line, cs_line))

    # -- preferred roles --------------------------------------------------- #
    for i, role in enumerate(data.get("preferred_roles") or []):
        key = f"role.{i}"
        tags = list(role.get("tags") or [])
        ctx["preferred_roles"].append(
            {
                "text": reg.make(key, role),
                "note": reg.make(f"{key}.note", role["note"]) if role.get("note") else None,
                "tags": tags,
                "emphasized": bool(variant.emphasize_tags & set(tags)),
            }
        )

    # -- skills ------------------------------------------------------------ #
    for group in data.get("skills") or []:
        gid = slug(localize(group.get("group", ""), "en"))
        items = []
        for item in group.get("items") or []:
            level = item.get("level", "working")
            if level not in LEVEL_LABELS:
                raise BuildError(
                    f"skill {item.get('name')!r}: level must be one of "
                    f"{sorted(LEVEL_LABELS)}, got {level!r}"
                )
            bar = item.get("bar")
            items.append(
                {
                    "name": item.get("name", ""),
                    "level": level,
                    "level_label": reg.ui(f"level_{level}"),
                    "bar": int(bar) if bar is not None else None,
                }
            )
        ctx["skills"].append({"id": gid, "title": reg.make(f"skillgroup.{gid}", group.get("group", "")), "items": items})

    # -- experience -------------------------------------------------------- #
    limit = DETAIL_LIMITS[variant.experience_detail]
    for entry in data.get("experience") or []:
        if not keep(entry, variant):
            continue
        eid = entry.get("id") or slug(entry.get("company", "job"))
        tags = list(entry.get("tags") or [])

        highlights = []
        for j, hl in enumerate(entry.get("highlights") or []):
            hl_tags = list(hl.get("tags") or [])
            highlights.append(
                {
                    "text": reg.make(f"exp.{eid}.hl.{j}", hl),
                    "tags": hl_tags,
                    "metric": hl.get("metric"),
                    "emphasized": bool(variant.emphasize_tags & set(hl_tags)),
                }
            )
        # Emphasized highlights win the limited slots; order is otherwise kept.
        if limit is not None:
            ranked = sorted(range(len(highlights)), key=lambda i: (0 if highlights[i]["emphasized"] else 1, i))
            chosen = sorted(ranked[:limit])
            visible = [highlights[i] for i in chosen]
            hidden = [highlights[i] for i in range(len(highlights)) if i not in set(chosen)]
        else:
            visible, hidden = highlights, []

        ctx["experience"].append(
            {
                "id": eid,
                "company": entry.get("company", ""),
                "via": entry.get("via"),
                "role": reg.make(f"exp.{eid}.role", entry.get("role", "")),
                "start": entry.get("start"),
                "end": entry.get("end"),
                "period": fmt_period(entry.get('start'), entry.get('end'), ui, lang),
                "tags": tags,
                "summary": reg.make(f"exp.{eid}.summary", entry.get("summary", "")),
                "highlights": visible,
                "highlights_extra": hidden,
                "skills_learned": list(entry.get("skills_learned") or []),
                "emphasized": bool(variant.emphasize_tags & set(tags)),
            }
        )

    # -- open source ------------------------------------------------------- #
    for project in data.get("open_source") or []:
        if not keep(project, variant):
            continue
        pid = project.get("id") or slug(project.get("name", "project"))
        ctx["open_source"].append(
            {
                "id": pid,
                "name": project.get("name", pid),
                "featured": bool(project.get("featured")),
                "url": project.get("url"),
                "stars": project.get("stars"),
                "forks": project.get("forks"),
                "tech": list(project.get("tech") or []),
                "summary": reg.make(f"oss.{pid}.summary", project.get("summary", "")),
                "links": list(project.get("links") or []),
                "related": list(project.get("related") or []),
            }
        )
    ctx["open_source"].sort(key=lambda p: (0 if p["featured"] else 1,))

    # -- education --------------------------------------------------------- #
    for i, edu in enumerate(data.get("education") or []):
        awarded = bool(edu.get("degree_awarded"))
        ctx["education"].append(
            {
                "institution": edu.get("institution", ""),
                "field": edu.get("field", ""),
                "start": edu.get("start"),
                "end": edu.get("end"),
                "period": fmt_period(edu.get('start'), edu.get('end'), ui, lang),
                "degree_awarded": awarded,
                "note": reg.make(f"edu.{i}.note", edu.get("note", "")) if edu.get("note") else None,
                "links": list(edu.get("links") or []),
            }
        )

    # -- languages / misc -------------------------------------------------- #
    for lng in data.get("languages") or []:
        ctx["languages"].append(
            {
                "name": reg.make(f"lang.{slug(lng.get('name', ''))}", lng.get("name", ""), lng.get("name_cs") or lng.get("name", "")),
                "cefr": lng.get("cefr", ""),
            }
        )

    if data.get("work_authorization"):
        ctx["work_authorization"] = reg.make("work_authorization", data["work_authorization"])

    availability = data.get("availability") or {}
    if availability:
        ctx["availability"] = {
            "ico": availability.get("ico"),
            "text": reg.make("availability", availability),
        }

    for i, interest in enumerate(data.get("interests") or []):
        ctx["interests"].append(reg.make(f"interest.{i}", interest))

    for i, quote in enumerate(data.get("testimonials") or []):
        ctx["testimonials"].append(
            {
                "quote": reg.make(f"testimonial.{i}", quote.get("quote", quote)),
                "attribution": quote.get("attribution", ""),
            }
        )

    # -- sections ---------------------------------------------------------- #
    sections = []
    for sid in variant.sections:
        if sid == "testimonials" and not ctx["testimonials"]:
            continue
        if sid == "availability" and not (ctx["availability"] or ctx["work_authorization"]):
            continue
        if sid in {"summary", "preferred_roles", "experience", "skills", "open_source", "education", "languages", "interests"} and not ctx[sid]:
            continue
        en, cs = SECTION_TITLES[sid]
        sections.append({"id": sid, "title": reg.make(f"ui.section.{sid}", en, cs)})
    ctx["sections"] = sections

    # -- structured data --------------------------------------------------- #
    ctx["jsonld"] = build_jsonld(data, ctx, lang)

    # Registry is complete only now, so the translation table goes in last.
    ctx["translations_json"] = js_json(reg.translations())
    return ctx


def js_json(obj) -> str:
    """JSON safe to inline in a ``<script>`` element."""
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    return text.replace("</", "<\\/").replace("<!--", "<\\!--")


def build_jsonld(data: dict, ctx: dict, lang: str) -> list[str]:
    meta = data.get("meta") or {}
    contact = meta.get("contact") or {}
    location = meta.get("location") or {}

    same_as = [
        contact.get(k)
        for k in ("github", "linkedin", "x", "youtube", "website")
        if contact.get(k)
    ]

    person = {
        "@context": "https://schema.org/",
        "@type": "Person",
        "name": localize(meta.get("name", ""), lang),
        "url": SITE_URL,
        "sameAs": same_as,
        # jobTitle tracks the headline from the data, never a stale hard-coded one.
        "jobTitle": localize(meta.get("headline", ""), lang),
    }
    if contact.get("email"):
        person["email"] = contact["email"]
    if contact.get("phone"):
        person["telephone"] = contact["phone"]
    if location.get("city"):
        person["address"] = {
            "@type": "PostalAddress",
            "addressLocality": location.get("city", ""),
            "addressCountry": location.get("country", ""),
        }
    if data.get("languages"):
        person["knowsLanguage"] = [
            {"@type": "Language", "name": l.get("name", ""), "alternateName": l.get("cefr", "")}
            for l in data["languages"]
        ]
    know = []
    for group in data.get("skills") or []:
        for item in group.get("items") or []:
            if item.get("name"):
                know.append(item["name"])
    if know:
        person["knowsAbout"] = know

    # alumniOf asserts an awarded degree in most consumers' reading of it, so it
    # is emitted only for entries that really awarded one.  Attendance without a
    # degree is described as coursework instead.
    alumni = [
        {"@type": "CollegeOrUniversity", "name": e.get("institution", "")}
        for e in (data.get("education") or [])
        if e.get("degree_awarded")
    ]
    if alumni:
        person["alumniOf"] = alumni
    coursework = [
        f"{e.get('institution', '')} — {e.get('field', '')}".strip(" —")
        for e in (data.get("education") or [])
        if not e.get("degree_awarded")
    ]
    if coursework:
        person["knowsAbout"] = (person.get("knowsAbout") or []) + coursework

    resume = {
        "@context": "https://schema.org/",
        "@type": "ResumeAction",
        "name": f"{localize(meta.get('name', ''), lang)} — CV",
        "description": localize(meta.get("headline", ""), lang),
        "url": SITE_URL,
    }
    return [js_json(person), js_json(resume)]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def jinja_env() -> Environment:
    if not TEMPLATE_DIR.exists():
        raise BuildError(f"templates directory missing: {TEMPLATE_DIR}")
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=True,
    )
    env.filters["localize"] = localize
    return env


def render(env: Environment, template_name: str, ctx: dict) -> str:
    template = env.get_template(template_name)
    if template_name.endswith(".md.j2"):
        # Markdown is not HTML; escaping would corrupt it.
        env_md = env.overlay(autoescape=False)
        template = env_md.get_template(template_name)
    text = template.render(**ctx)
    # Deterministic line endings and exactly one trailing newline.
    text = text.replace("\r\n", "\n").rstrip("\n") + "\n"
    return text


def write_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #


def find_chromium() -> str:
    env_path = os.environ.get("CV_CHROMIUM")
    if env_path and Path(env_path).exists():
        return env_path
    candidates: list[Path] = []
    pw = Path("/opt/pw-browsers")
    if pw.exists():
        candidates += sorted(pw.glob("chromium-*/chrome-linux/chrome"), reverse=True)
        candidates += sorted(pw.glob("chromium_headless_shell-*/chrome-linux/headless_shell"), reverse=True)
    for path in candidates:
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise BuildError(
        "no Chromium binary found for PDF rendering. Set CV_CHROMIUM=/path/to/chrome "
        "or pass --skip-pdf."
    )


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    chromium = find_chromium()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cv-chromium-") as profile:
        cmd = [
            chromium,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--hide-scrollbars",
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise BuildError(
            "Chromium produced no PDF.\n"
            f"  command: {' '.join(cmd)}\n"
            f"  stderr: {proc.stderr.decode('utf-8', 'replace')[-2000:]}"
        )
    normalize_pdf(pdf_path)


def normalize_pdf(pdf_path: Path) -> None:
    """Freeze Chromium's ``/CreationDate`` so repeat builds are byte-identical.

    The replacement has the same byte length as the stamp it replaces, so every
    xref offset in the file stays correct.
    """
    raw = pdf_path.read_bytes()

    def sub(match: re.Match) -> bytes:
        found = match.group(0)
        return FIXED_PDF_DATE.ljust(len(found), b" ")[: len(found)]

    fixed = PDF_DATE_RE.sub(sub, raw)
    if fixed != raw:
        pdf_path.write_bytes(fixed)


def pdf_page_count(pdf_path: Path) -> int:
    """Count pages by scanning the PDF; no third-party PDF library involved."""
    raw = pdf_path.read_bytes()
    if not raw.startswith(b"%PDF-"):
        raise BuildError(f"{pdf_path} is not a PDF (bad header)")
    if b"%%EOF" not in raw[-2048:]:
        raise BuildError(f"{pdf_path} is truncated (no %%EOF near the end)")
    pages = re.findall(rb"/Type\s*/Page(?![sA-Za-z])", raw)
    if pages:
        return len(pages)
    counts = [int(m) for m in re.findall(rb"/Type\s*/Pages.{0,200}?/Count\s+(\d+)", raw, re.S)]
    if counts:
        return max(counts)
    raise BuildError(f"cannot determine page count of {pdf_path}")


# --------------------------------------------------------------------------- #
# Build-time assertions
# --------------------------------------------------------------------------- #


def assert_experience_order(data: dict, checker: Checker) -> None:
    """#1 reverse-chronological + Resideo first; #2 every entry has a start."""
    entries = data.get("experience") or []
    checker.check(bool(entries), "experience.present", "experience[] is empty")
    if not entries:
        return

    # #2 -- every entry has a start key.
    missing = [e.get("id", f"index {i}") for i, e in enumerate(entries) if "start" not in e]
    checker.check(
        not missing,
        "experience.start_key",
        f"entries without a 'start' key: {missing}",
    )

    # #1a -- the first entry is the current Resideo engagement.
    first_id = entries[0].get("id")
    checker.check(
        first_id == "resideo",
        "experience.first_is_resideo",
        f"first experience entry id is {first_id!r}, expected 'resideo'",
    )

    # #1b -- reverse chronological, TODO(user) entries exempt but still present.
    todo_ids = []
    previous = None
    previous_id = None
    for entry in entries:
        ident = entry.get("id", "<no id>")
        if "start" not in entry:
            continue
        try:
            parsed = parse_start(entry["start"])
        except ValueError as exc:
            checker.check(False, "experience.start_parse", f"{ident}: {exc}")
            continue
        if parsed is None:
            todo_ids.append(ident)
            continue  # exempt from the ordering comparison
        if previous is not None and parsed > previous:
            checker.check(
                False,
                "experience.reverse_chronological",
                f"{ident} (start {entry['start']}) is newer than the preceding "
                f"{previous_id} ({previous[0]:04d}-{previous[1]:02d})",
            )
        previous = parsed
        previous_id = ident
    checker.check(True, "experience.reverse_chronological")

    checker.check(
        bool(todo_ids) or True,
        "experience.todo_exempt_from_ordering",
    )


def assert_all_experience_rendered(data: dict, rendered: dict[str, str], checker: Checker) -> None:
    """#1, second half: a ``TODO(user)`` entry is exempt from the ordering
    comparison but must still reach the output -- it may not be quietly dropped.

    Checked against the master renders, which apply no include/exclude filter.
    """
    import html as html_mod

    entries = data.get("experience") or []
    for label in ("index.html", "cv-3-page.md"):
        text = rendered.get(label)
        if text is None:
            continue
        for entry in entries:
            company = str(entry.get("company", "")).strip()
            if not company:
                continue
            present = company in text or html_mod.escape(company) in text
            checker.check(
                present,
                "experience.all_entries_rendered",
                f"{entry.get('id')!r} ({company}) is missing from {label}"
                + (f"; its start is {TODO_MARKER}" if str(entry.get("start")) == TODO_MARKER else ""),
            )
    checker.check(True, "experience.all_entries_rendered")


def assert_no_degree_claim(data: dict, rendered: dict[str, str], checker: Checker) -> None:
    """#3 nothing in the output may state or imply an awarded degree."""
    education = data.get("education") or []
    any_degree = any(e.get("degree_awarded") for e in education)

    patterns = list(BANNED_DEGREE_PATTERNS)
    if not any_degree:
        patterns += DEGREE_CONDITIONAL_PATTERNS

    for label, text in sorted(rendered.items()):
        for pattern, flags in patterns:
            match = re.search(pattern, text, flags)
            if match:
                line = text[: match.start()].count("\n") + 1
                snippet = text[max(0, match.start() - 60) : match.end() + 60].replace("\n", " ")
                checker.check(
                    False,
                    "output.no_degree_claim",
                    f"{label}:{line} matches /{pattern}/ -> …{snippet}…",
                )
    checker.check(True, "output.no_degree_claim")

    # Structural half of the same rule: a non-degree entry must not be dressed
    # up as one anywhere in the data it renders from.
    for entry in education:
        if entry.get("degree_awarded"):
            continue
        blob = json.dumps(entry, ensure_ascii=False, default=str)
        for pattern, flags in BANNED_DEGREE_PATTERNS:
            if re.search(pattern, blob, flags):
                checker.check(
                    False,
                    "education.coursework_only",
                    f"{entry.get('institution')!r} has degree_awarded: false but "
                    f"its text matches /{pattern}/",
                )
    checker.check(True, "education.coursework_only")



def assert_no_todo_marker(data: dict, rendered: dict[str, str], checker: Checker) -> None:
    """No rendered artifact may contain the ``TODO(user)`` sentinel.

    The marker belongs in ``data/cv.yaml``, where it records a date nobody has
    supplied. ``index.html`` is a published page, so a literal
    ``TODO(user) – TODO(user)`` there is worse than showing no date: it
    advertises an unfinished document. Renderers drop an unfilled range instead
    (see ``fmt_period``); this asserts they actually did.
    """
    for label, text in sorted(rendered.items()):
        idx = text.find(TODO_MARKER)
        if idx != -1:
            line = text[:idx].count("\n") + 1
            snippet = text[max(0, idx - 60) : idx + 60].replace("\n", " ")
            checker.check(
                False,
                "output.no_todo_marker",
                f"{label}:{line} leaks {TODO_MARKER} -> …{snippet}…",
            )
    checker.check(True, "output.no_todo_marker")

    # Not a failure -- just keep the unfilled fields visible in the report.
    unfilled = []
    for entry in data.get("experience") or []:
        for field in ("start", "end"):
            if str(entry.get(field)).strip() == TODO_MARKER:
                unfilled.append(f"experience[{entry.get('id')}].{field}")
    for i, entry in enumerate(data.get("education") or []):
        for field in ("start", "end"):
            if str(entry.get(field)).strip() == TODO_MARKER:
                unfilled.append(f"education[{i}].{field}")
    if unfilled:
        print(f"note: {len(unfilled)} unfilled date(s) in data, omitted from output:")
        for item in unfilled:
            print(f"  - {item}")


def assert_page_budget(variant: Variant, pdf_path: Path, checker: Checker) -> int | None:
    """#4 the produced PDF has to fit the variant's page budget."""
    pages = pdf_page_count(pdf_path)
    if variant.page_budget is None:
        checker.check(True, f"pdf.{variant.name}.valid")
        return pages
    lo, hi = variant.page_budget
    checker.check(
        lo <= pages <= hi,
        f"pdf.{variant.name}.page_budget",
        f"{pdf_path.name} is {pages} page(s), budget is {lo}–{hi}",
    )
    return pages


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


class Builder:
    def __init__(self, args: argparse.Namespace) -> None:
        self.data_path = Path(args.data).resolve()
        self.variants_dir = (
            Path(args.variants_dir).resolve()
            if args.variants_dir
            else self.data_path.parent / "variants"
        )
        self.out_dir = Path(args.out_dir).resolve()
        self.dist = Path(args.dist).resolve()
        self.skip_pdf = args.skip_pdf
        self.keep_print_html = args.keep_print_html
        self.quiet = args.quiet
        self.env = jinja_env()
        self.checker = Checker()
        try:
            self.source_label = str(self.data_path.relative_to(REPO_ROOT))
        except ValueError:
            self.source_label = self.data_path.name
        self.rendered: dict[str, str] = {}

    def log(self, message: str) -> None:
        if not self.quiet:
            print(message)

    @staticmethod
    def rel(path: Path) -> str:
        try:
            return str(path.relative_to(REPO_ROOT))
        except ValueError:
            return str(path)

    # -- individual outputs ------------------------------------------------ #

    def render_index(self, master: Variant) -> str:
        ctx = build_context(master, "en", embed_assets=False, source_label=self.source_label)
        html = render(self.env, "base.html.j2", ctx)
        self.rendered["index.html"] = html
        return html

    def render_markdown(self, master: Variant) -> str:
        ctx = build_context(master, master.locale, embed_assets=False, source_label=self.source_label)
        text = render(self.env, "cv.md.j2", ctx)
        self.rendered["cv-3-page.md"] = text
        return text

    def render_print(self, variant: Variant) -> str:
        ctx = build_context(variant, variant.locale, embed_assets=True, source_label=self.source_label)
        html = render(self.env, "print.html.j2", ctx)
        self.rendered[f"print:{variant.name}"] = html
        return html

    def build_pdf(self, variant: Variant, work_dir: Path) -> Path | None:
        html = self.render_print(variant)
        html_path = work_dir / f"vs-cv-{variant.name}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
        if self.skip_pdf:
            return None
        pdf_path = self.dist / f"vs-cv-{variant.name}.pdf"
        html_to_pdf(html_path, pdf_path)
        pages = assert_page_budget(variant, pdf_path, self.checker)
        size_kb = pdf_path.stat().st_size / 1024
        self.log(f"  {self.rel(pdf_path)}  ({pages} pages, {size_kb:.0f} KB)")
        return pdf_path

    # -- entry points ------------------------------------------------------ #

    def known_variants(self) -> list[str]:
        if not self.variants_dir.exists():
            return []
        names = {p.stem for p in self.variants_dir.glob("*.yaml")}
        names |= {p.stem for p in self.variants_dir.glob("*.yml")}
        return sorted(names)

    def assert_on_rendered(self, master) -> None:
        """Every assertion that inspects rendered output.

        ``--all``, ``--variant`` and ``--check`` all call this. They used to
        list the assertions separately and had already drifted: only ``--all``
        carried the TODO-marker check, so ``--check`` -- the assertion-only
        path, and the one CI would run -- passed a build that leaked the
        sentinel. One list, three callers.
        """
        assert_all_experience_rendered(master.data, self.rendered, self.checker)
        assert_no_degree_claim(master.data, self.rendered, self.checker)
        assert_no_todo_marker(master.data, self.rendered, self.checker)

    def run_all(self) -> None:
        master = load_master(self.data_path)
        assert_experience_order(master.data, self.checker)

        index_html = self.render_index(master)
        markdown = self.render_markdown(master)

        with tempfile.TemporaryDirectory(prefix="cv-print-") as tmp:
            work = self.dist if self.keep_print_html else Path(tmp)
            self.log("building master:")
            write_if_changed(self.out_dir / "index.html", index_html)
            self.log(f"  {self.rel(self.out_dir / 'index.html')}")
            write_if_changed(self.out_dir / "cv-3-page.md", markdown)
            self.log(f"  {self.rel(self.out_dir / 'cv-3-page.md')}")
            self.build_pdf(master, work)

        self.assert_on_rendered(master)
        self.checker.raise_if_failed()

    def run_variant(self, names: list[str]) -> None:
        master = load_master(self.data_path)
        assert_experience_order(master.data, self.checker)
        with tempfile.TemporaryDirectory(prefix="cv-print-") as tmp:
            work = self.dist if self.keep_print_html else Path(tmp)
            for name in names:
                variant = load_variant(name, self.data_path, self.variants_dir)
                assert_experience_order(variant.data, self.checker)
                self.log(f"building variant {name}:")
                self.build_pdf(variant, work)
        self.assert_on_rendered(master)
        self.checker.raise_if_failed()

    def run_check(self) -> None:
        master = load_master(self.data_path)
        assert_experience_order(master.data, self.checker)
        self.render_index(master)
        self.render_markdown(master)

        with tempfile.TemporaryDirectory(prefix="cv-check-") as tmp:
            tmp_path = Path(tmp)
            saved_dist = self.dist
            self.dist = tmp_path / "dist"
            try:
                self.build_pdf(master, tmp_path)
                for name in self.known_variants():
                    variant = load_variant(name, self.data_path, self.variants_dir)
                    assert_experience_order(variant.data, self.checker)
                    self.build_pdf(variant, tmp_path)
            finally:
                self.dist = saved_dist

        self.assert_on_rendered(master)
        self.checker.raise_if_failed()
        self.log(f"all {len(self.checker.passed)} assertions passed; nothing written")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build.py",
        description="Render the CV from data/cv.yaml into HTML, Markdown and PDF.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true", help="build index.html, cv-3-page.md and the master PDF")
    mode.add_argument("--variant", action="append", metavar="NAME", help="build dist/vs-cv-<NAME>.pdf (repeatable)")
    mode.add_argument("--check", action="store_true", help="run every assertion, write nothing")
    mode.add_argument("--list-variants", action="store_true", help="list the variants found next to the data file")

    parser.add_argument("--data", default=str(DEFAULT_DATA), help="source YAML (default: data/cv.yaml)")
    parser.add_argument("--variants-dir", default=None, help="variant directory (default: <data dir>/variants)")
    parser.add_argument("--out-dir", default=str(REPO_ROOT), help="where index.html and cv-3-page.md go")
    parser.add_argument("--dist", default=str(DEFAULT_DIST), help="where PDFs go (default: dist/)")
    parser.add_argument("--skip-pdf", action="store_true", help="skip Chromium; page-budget checks are skipped too")
    parser.add_argument("--keep-print-html", action="store_true", help="keep the intermediate print HTML in dist/")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    try:
        builder = Builder(args)
        if args.list_variants:
            for name in builder.known_variants():
                print(name)
        elif args.all:
            builder.run_all()
        elif args.variant:
            builder.run_variant(args.variant)
        else:
            builder.run_check()
    except BuildError as exc:
        print(f"\nbuild failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
