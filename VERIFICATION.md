# Verification report

Scope: branch `claude/part-a-subagents-plan-x2s5hb`, commit `d585710`, verified 2026-09-16.
Method: rebuilt every artifact twice, diffed the generated master against all three "before"
sources (`git show 066c7d1:index.html`, `git show 066c7d1:cv-3-page.md`, the PDF text extraction),
loaded `index.html` in headless Chromium, HEAD-checked all 46 outbound URLs, and extracted the text
of all four PDFs with a purpose-written CMap-based extractor.

---

## Verdict

**The build system passes every mechanical check.** Reproducible to the byte, 40 assertions green,
no degree claim anywhere, no `TODO(user)` leak, correct chronology, all page budgets met, the web
page runs clean in a browser, and `pl-b2b` is free of ASPICE/AUTOSAR/QNX.

**What is not clean is the content the build faithfully renders.** Three links on the CV are dead,
one listed "project" is a fork of somebody else's repository, a project that exists in the data
(`mcp-prompts-rs`) reaches no output at all, and twelve dates — including those of the current
headline role — are still blank because nobody has supplied them. None of this is a build bug;
all of it is visible to a reader of the published CV.

Nothing found here blocks the restructuring itself. Four items should be fixed before the CV is
sent anywhere: the dead links, the `mcp-servers` entry, the missing dates, and the stale
`vs-cv-sparesparrow.pdf` still served from the site root.

---

# Failures and items needing attention

## A. Needs the user — facts only he has

### A1. Twelve dates are unfilled; the most recent role prints with no period at all — HIGH
`data/cv.yaml:147-148` (resideo), `:377-378` (selfemployed), `:643-644`, `:651-652`, `:660-661`,
`:671-672` (all four education entries).

`fmt_period()` correctly renders an unfilled range as *no range* rather than leaking the sentinel,
and `--check` reports each one. The consequence, though, is that the CV's strongest and most recent
entry — Resideo (Ademco), the one the whole restructuring was done to surface — appears in every
artifact with **no dates whatsoever**, directly above Thermo Fisher's "2023 – 2024". A reader will
read that as an unexplained gap, or as concealment. Same for Self-employed and for all of Education.

`2012 – 2014` for Masaryk was present in the old `index.html` and is recoverable (see C4); the other
ten are not in any source document.

**Action:** supply the six experience dates and four education ranges in `data/cv.yaml`.

## B. Wrong or broken in the published output

### B1. `mcp-servers` is a fork of the upstream MCP reference repo, presented as his own suite — HIGH
`data/cv.yaml:529-538`; rendered at `cv-3-page.md:231-237` and `index.html` (Open Source section).

The CV says: *"A suite of Model Context Protocol servers: mermaid (diagram generator), solid (SOLID
code review), prompt-manager (prompt orchestration and templates) and more."*

`https://raw.githubusercontent.com/sparesparrow/mcp-servers/main/README.md` returns the verbatim
`modelcontextprotocol/servers` reference README (68 KB, **zero** occurrences of "sparesparrow", no
mermaid/solid/prompt-manager entries). `src/mermaid/`, `src/solid/`, `src/prompt-manager/` and
`src/prompts/` all 404 on `main`. The repo is also absent from `user:sparesparrow` repo search
(total_count 62), which excludes forks — consistent with it being a fork.

This claim came in from the old `index.html`, so it is "traceable to a source document", but the
source was wrong. Presenting a fork of Anthropic's reference-server repository as a personal project
is the single highest-risk item on this CV: it is trivially checkable by any technical reviewer.

**Action:** delete the entry, or rewrite it to describe the actual contribution (if the custom
servers live on a non-default branch, say so and link that branch).

### B2. Three dead outbound links — HIGH
A dead link on a CV is worse than an omitted one, and all three sit in the MCP-Prompts link row,
which is the CV's main open-source credibility exhibit.

| Link | `data/cv.yaml` | Status | Diagnosis |
|---|---|---|---|
| `https://hub.docker.com/layers/sparesparrow/mcp-prompts/` | `:443` | **404** | Real. `/layers/` needs `<user>/<repo>/<tag>/<digest>`. `https://hub.docker.com/r/sparesparrow/mcp-prompts` returns **200** through the same proxy — use that. |
| `https://glama.fly.dev/mcp/servers/@sparesparrow/mcp-prompts/` | `:446` | **NXDOMAIN** | Real. `glama.fly.dev` no longer resolves; the Fly deployment is gone. Redundant anyway — `glama.ai` (`:445`) works. |
| `https://www.magicslides.app/mcps/sparesparrow-prompt-manager` | `:448` | **soft 404** | Real. HTTP 200 but the page title is `Error - MCP Server`. |

Two more could not be settled from this sandbox and need a check from a normal browser:
- `https://mcphub.com/mcp-servers/sparesparrow/mcp-prompts-rs` (`:449`) — the egress gateway answered
  502 to CONNECT. DNS resolves. **Unverified.**
- `https://www.pulsemcp.com/servers/sparesparrow-project-orchestrator` (`:451`) — Cloudflare 403
  ("Attention Required"), i.e. bot protection, not necessarily a dead page. **Unverified.**

Everything else resolves. `github.com`/`npmjs.com` returned 403 and `linkedin.com` 999 through the
proxy; all were re-verified out of band (GitHub repo search, `registry.npmjs.org` 200) and are fine.
`crates.io/crates/rust-network-mgr` returned 404 to curl but the crate is real —
`crates.io/api/v1/crates/rust-network-mgr` returns 200 with seven published versions.

### B3. `mcp-prompts-rs` is in the data but reaches no output — MEDIUM
`data/cv.yaml:453-459` defines an `open_source[].related` entry with a name, URL and bilingual
summary. `build.py:686` copies `related` into the render context. **No template consumes it** —
`grep -n related templates/*.j2` returns nothing.

Result: the Rust reimplementation of MCP-Prompts, described in the old `cv-3-page.md`, appears in no
artifact. The string `mcp-prompts-rs` survives in the outputs only by accident, inside the MCPHub
URL. This is the one genuine *silent* drop found: data written, loaded, and discarded without a
warning.

**Action:** render `related` (the print templates are the tight ones; `base.html.j2` and
`cv.md.j2` have room), or drop the key from the data so nothing pretends to carry it.

### B4. Education links are dropped from Markdown; one URL is dropped from everything — MEDIUM
- `templates/cv.md.j2:81-90` renders institution, field, period and note but never `item.links`.
  Compare `templates/base.html.j2:439`, which does. So `cv-3-page.md` silently loses the
  refactoring.guru, Hack The Box and three Audible links that the old `cv-3-page.md` carried inline.
- `data/cv.yaml:657` sets `url:` on the Coursera entry, but `build_context()` (`build.py:694-706`)
  builds the education dict without a `url` key. The Deep Learning Specialization link — present in
  the old `index.html` — is therefore rendered nowhere. Dead data.

### B5. Markdown paragraph breaks are eaten by `trim_blocks` — MEDIUM (cosmetic, but in a published file)
`templates/cv.md.j2:41` and `:83` end with an inline `{% endif %}`. Jinja's `trim_blocks=True`
(`build.py:846`) removes the first newline after a **block** tag, so the newline that ends those
lines disappears.

- Line 83 → the disclaimer is glued onto the institution line:
  `cv-3-page.md:315,317,319,321` read
  `- **Masaryk University, Faculty of Informatics** — Computer Science  - *Coursework only — no academic title*`
  instead of making it a sub-bullet.
- Line 41 → the blank line between the company line and the role summary is consumed, e.g.
  `cv-3-page.md:37-38`. Every Markdown renderer (GitHub included) will join those into one
  paragraph: *"**Resideo (Ademco)** (via CoolPeople (contractor)) Hardware-in-the-loop
  verification of …"*. This affects all six experience entries.

Fix: `{%- endif %}` → no, that strips the wrong side; use `{% endif -%}`-free form by moving the
conditional inline (`{{ ' · ' ~ item.period if item.period else '' }}`), which is already the
pattern used on `cv.md.j2:61`.

### B6. Skill level labels do not switch to Czech — MEDIUM
`templates/base.html.j2:395` emits `<span>{{ item.name }} <em>({{ item.level_label }})</em></span>`
with no `data-i18n` attribute. The `translations` table *does* contain `ui.level_senior`,
`ui.level_medior` and `ui.level_working`, and nothing uses them.

`Senior`/`Medior` are identical in both languages so nothing shows, but **`Working knowledge` stays
English in the Czech view** — 7 occurrences (Qt/QML, Rust, Enterprise Architect …). The Czech string
`Pracovní znalost` exists in the table and is unreachable.

Two other visible English strings do not switch, for the same structural reason (institution names
are not passed through the i18n registry): `Self-directed study` and `Professional development
reading` (`data/cv.yaml:658,669`). These are descriptive phrases, not proper nouns, so they read as
untranslated in the Czech view.

### B7. `IČO` is stated twice in one paragraph — LOW
`data/cv.yaml:700-701`: the `availability.en` text already contains "(Czech IČO)", and `ico: true`
additionally makes the templates print `ui.ico_yes` = "Trading on a Czech IČO". Every artifact with
an availability section reads:

> Available as an independent contractor (Czech IČO). Brno on-site and remote. Trading on a Czech IČO.

Drop one of the two.

### B8. A superseded CV is still published at the site root — MEDIUM
`vs-cv-sparesparrow.pdf` (tracked, last touched in `d729b79`, pre-restructuring) still sits in the
repo root and is therefore live at `https://sparesparrow.github.io/cv/vs-cv-sparesparrow.pdf`. It
carries exactly the claims the restructuring removed on purpose — "almost 3 years (I am all-in AI
since GPT-3)", "Rust *(Junior)*", "Qt/QML Developer *(Junior)*", the two separate IBM roles.

The new `index.html:326` correctly points its download button at `dist/vs-cv-master.pdf`, but anyone
with the old URL, or any search engine that indexed it, still gets the old document.

**Action:** delete it, or replace its bytes with `dist/vs-cv-master.pdf`.

### B9. `README.md` still documents the old hand-edited workflow — MEDIUM
`README.md:9-20` tells readers to "Open `index.html`" and invites "Pull requests … for typo fixes" —
i.e. it points contributors (and the user, in six months) straight at the generated file that now
carries `<!-- DO NOT EDIT — generated by build.py -->`. It never mentions `data/cv.yaml`, `build.py`,
the variants or `--check`. This is how the original drift started.

### B10. Nothing enforces `build.py --check` — MEDIUM
There is no `.github/` directory. The 40 assertions — including the degree guard and the TODO-leak
guard — only run when somebody remembers to run them. A three-line workflow calling
`python3 build.py --check` on push would make the guarantee real. (Note: `--check` needs Chromium;
`--skip-pdf` weakens it to the non-PDF assertions.)

### B11. Star/fork counts are stale — LOW
The CV says MCP-Prompts has "97 stars and 21 forks" (`data/cv.yaml:434-435`, repeated in
`summary.3`). Live figures via the GitHub API: **118 stars, 20 forks**. Stars understate the truth
by 21; forks *over*state it by one. `rtp-midi`'s "2 stars" is accurate. Worth noting that
`cursor-rules` (73 stars) is listed without any count, which undersells it.

## C. Content present in the "before" sources that is gone, beyond the agreed removals

The agreed removals were all verified as intentional and correctly executed: the two IBM roles are
condensed into one (`data/cv.yaml:380-400`), the "all-in AI since GPT-3 / almost 3 years" claim is
gone, "6+ years of experience" is gone, "Bachelor's Degree" is gone from the Masaryk entry, the three
anonymous testimonials are gone, the Podman "40%" metric is gone, and Rust and Qt/QML are demoted
from *Junior* to *Working knowledge* (`data/cv.yaml`, level `working`).

Everything below is additional. None of it is severe; it is listed because the brief asked for
anything else missing to be named explicitly.

- **C1. MCP-Prompts open-source metrics.** Old `index.html`: *"Wrote integration tests, increasing
  code coverage by 25% and reducing bug reports by 30%."* The new summary keeps "Implemented a
  hexagonal architecture and integration tests" but drops both figures. Same class as the agreed
  Podman "40%" removal, so probably deliberate — but it was not on the list.
- **C2. `human-action` metric.** Old `index.html`: *"Reduces manual narration time by 90% through
  automated voice synthesis."* Gone. Same class as C1.
- **C3. The Czech-only "About" paragraph.** Old `index.html` carried a Czech passage with no English
  counterpart: learning Rust and React, and a statement that open source is a necessary branch of
  development *"vzhledem k možným dopadům centralizace AI na svobodu a suverenitu jednotlivce"*. It
  has no equivalent in the new data. That was the only piece of personal positioning on the old page
  and it is now absent from both languages.
- **C4. Masaryk dates and field name.** Old `index.html`: *"Informatics - Computer Systems and Data
  Processing, Bachelor's Degree, 2012 – 2014"*. The degree is correctly gone; **the 2012–2014 dates
  went with it**, and the field was rewritten to the more generic "Computer Science". The dates are
  recoverable from the old source and should go back in (see A1).
- **C5. Other duration figures.** Old `index.html` About: *"Linux for over 8 years"*, *"4 years of
  experience with networking and containerization"*, *"over 4 years with Python and TypeScript"*.
  All gone alongside the agreed "6+ years" removal — consistent treatment, but not itemised.
- **C6. Self-descriptors.** *"Researcher"* and *"MCP Server Architect"* (old `index.html` headline)
  and the old *"Whoami"* framing do not survive. Judgement call; the new headline is stronger.
- **C7. Preferred-role keywords.** The old role tag list included *Backend* and *Data Processing*,
  which appear nowhere in the new preferred-roles block. They are implicitly covered by the skills
  grid. Low impact, but it is keyword surface lost to an ATS.

Everything else checks out. Every substantive Resideo, Thermo Fisher, Honeywell, TNS, Self-employed
and IBM bullet from all three sources is present in the generated master; every open-source project
from the old `index.html` and old `cv-3-page.md` is present (`mcp-servers` — see B1); the Glama
badge (`data/cv.yaml:42`), the Signal/YouTube/Discord/Calendly links, "VirtualBox, GDB", the
Certified Ethical Hacker note and all six "New Skills Learned" blocks survive intact.

## D. Claims in the output not traceable to any source document

None are implausible; all are unverifiable from the source material and should be confirmed by the
user before the CV goes out.

- **Languages** (`data/cv.yaml:682-686`): Czech native, Slovak native, English **C1**, German **A1**.
  No before-source mentions languages at all. The CEFR levels in particular are assertions a
  recruiter may test.
- **Location and availability** (`data/cv.yaml:699-702`, `:688`): "Brno, CZ", "Available as an
  independent contractor (Czech IČO)", "EU citizen (Czech Republic) — no permit required in the
  EU/EEA". Consistent with the Brno employer history and almost certainly true, but new.
- **Swiss variant only** (`data/cv.yaml:696`, `templates/swiss.html.j2:42`): "**B-permit eligible**" and "two to three
  referees and work certificates (**Arbeitszeugnisse**) can be provided on request". Both are
  ordinary Swiss-dossier conventions and both are true-by-construction for an EU citizen, but they
  are new assertions, and the Arbeitszeugnisse one promises documents he may not hold from Czech
  employers.
- **Numeric skill bars** (`95/100`, `80/100`, …): self-assessments with no basis in the sources. They
  were bars in the old `index.html` too, so the form is inherited; the specific numbers are new.
- **LinkedIn URL**: the two before-sources disagreed — old `cv-3-page.md` had
  `linkedin.com/in/vojtěch-špaček-b22a211a3`, old `index.html` had `linkedin.com/in/sparesparrow`.
  The build kept the vanity URL. LinkedIn answers 999 to any non-browser request, so it could not be
  verified here. Confirm the vanity URL is the live profile.

## E. Proofing

Real errors only; technical terms, product names and deliberate style were not flagged.

- **`data/cv.yaml:190` — spelling variety.** "special**ised**" is the only `-ise` form in the entire
  corpus, against "Optimized", "categorization", "organization", "serialization", "virtualization",
  "containerized". Pick one variety; the rest of the document is US.
- **`data/cv.yaml:713` — comma splice.** *"Music production, and producing a Czech
  audiobook — a TTS narration of Mises' Human Action"*. The comma before "and" joining two noun
  phrases is wrong. Drop it.
- **`templates/swiss.html.j2:42` — repetition.** *"References available **on request** —
  two to three referees and work certificates (Arbeitszeugnisse) can be provided **on request**."*
  One sentence, same phrase twice.
- **Czech translation, `summary.1` and `exp.resideo.summary`** — *"gas furnace"* is rendered
  *"plynového kotle"*, which means **gas boiler**. A Czech HVAC reader will read a different product
  class. *"plynové teplovzdušné jednotky"* or leaving "furnace" in English would be accurate.
  Judgement call; flagged because the product is the centrepiece of the strongest entry.
- The Czech translation is otherwise good: idiomatic, correct decimal comma ("95,6 %"), correct
  declension of company names ("v Honeywellu", "ipmonu"). No grammar errors found.
- The English of all four variants is otherwise clean. No doubled words, no agreement errors, no
  typos found across `cv-3-page.md` and the extracted text of all four PDFs.

---

# Passes

### 1. Reproducibility — PASS
`python3 build.py --all` plus `--variant {cz-contractor,pl-b2b,ch}`, run twice. All seven artifacts
byte-identical across runs:

```
be8f05e59659214aac78b5239dac1adb  index.html
efaf97ad2b41033c9f88dd97c1747ff4  cv-3-page.md
b72d3528d98c141b489789754cc39d8b  dist/vs-cv-master.pdf
02878266bc76b772c255804a2c3a879c  dist/vs-cv-cz-contractor.pdf
afc1aa7f06e2e866fb1a57af00c67d12  dist/vs-cv-pl-b2b.pdf
96d0f0e035060ef33789244145e38f40  dist/vs-cv-ch.pdf
```

Stronger than asked: these also match the **committed** bytes exactly — `git status` is clean after
a full rebuild. The `/CreationDate` normalisation (`build.py:931-944`, equal-length substitution so
xref offsets stay valid) is what makes the PDFs deterministic, and it works.

### 2. Assertions — PASS
`python3 build.py --check` → **all 40 assertions passed; nothing written**, exit code **0**. It
renders the master plus all three variants into a temp dir, so the PDF page-budget assertions run
too. It also prints the 12 unfilled dates as a non-fatal note (see A1) — the right call: visible to
the maintainer, invisible to the reader.

### 3. Nothing silently dropped — PASS with exceptions
See sections B3 and C. One genuine silent drop (`mcp-prompts-rs`, B3) and two rendering gaps (B4).
All agreed removals verified as executed. No experience bullet, no "New Skills Learned" block and
no project from any of the three before-sources is missing from the generated master.

### 4. No degree claim — PASS
`grep -ri "bachelor\|bc\.\|mgr\.\|diploma"` across the working tree (excluding `.git`) produces only
false positives: three hits on the project name `rust-network-**mgr**.` at sentence end
(`index.html:742,1163,1306`) and the pattern literal at `build.py:161`. The same grep over the
extracted text of all four PDFs returns nothing.

`alumniOf` appears **zero** times in `index.html` — correct, since `degree_awarded` is false on every
education entry and `build.py:810-816` only emits `alumniOf` for entries that awarded one. Attendance
is expressed as `knowsAbout` coursework strings instead, and each entry is labelled
*"Coursework only — no academic title"*. The guard is also structural, not just textual: it
re-scans the education data itself (`build.py:1074-1086`).

### 5. No TODO sentinel in output — PASS
`TODO(user)` appears in `data/cv.yaml` (13 occurrences: one in the header comment, 12 real),
`build.py`, `fixtures/sample-cv.yaml`, and `templates/swiss.html.j2:176` — that last one inside a
Jinja `{#- … -#}` comment, so it is stripped before render (verified: `grep -c TODO
dist/vs-cv-ch.html` → 0). No rendered artifact contains it: not `index.html`, not `cv-3-page.md`,
not any print HTML, not any PDF.

**12 unfilled dates remain**, in these fields:
`experience[resideo].start`, `experience[resideo].end`, `experience[selfemployed].start`,
`experience[selfemployed].end`, `education[0..3].start`, `education[0..3].end`. See A1.

### 6. Chronology — PASS
`index.html` order (`:370, :394, :414, :434, :456, :472`) and `cv-3-page.md` order are identical:
**Resideo (Ademco)** → Thermo Fisher Scientific (2023–2024) → Honeywell (2022–2023) → Trusted
Network Solutions (2020–2022) → Self-employed → IBM (2014–2016). Reverse-chronological, Resideo
first. The assertion `experience.first_is_resideo` enforces the first position independently of the
date comparison, which is what makes it hold while Resideo's dates are blank.

### 7. Page budgets — PASS
| Variant | Pages | Budget | |
|---|---|---|---|
| master | 7 | none declared | OK |
| cz-contractor | 2 | `[1, 2]` | OK |
| pl-b2b | 2 | `{max: 2}` | OK |
| ch | **2** | `[2, 2]` — exact | **OK, exactly 2** |

Note: the master is 7 pages while the Markdown artifact is still named `cv-3-page.md`. Not a
failure — the master carries 17 open-source projects and full-detail highlights by design — but the
filename is now misleading. Judgement call.

### 8. The web page works — PASS
Loaded an instrumented copy in `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`
(`--headless --disable-gpu --no-sandbox --virtual-time-budget=10000 --dump-dom`).

- **JS console errors: zero.** Chromium's stderr under `--enable-logging=stderr` contains only D-Bus
  and Bluetooth noise from the sandbox, no `ERROR:CONSOLE`. The five `window.onerror` capture-phase
  events are resource-load failures for the offline CDN/QR/badge images, not script errors.
- **`setLanguage`: exactly one definition** (`function setLanguage`, confirmed statically and as
  `typeof setLanguage === "function"` at runtime).
- **i18n coverage:** 143 `data-i18n` elements (130 unique keys) + 2 `data-i18n-aria`; the
  `translations` table holds 141 keys, `en` and `cs` key sets identical. **No element references a
  key missing from the table.** Eleven table keys are used by no element:
  `ui.back_to_top` and `ui.lang_toggle_aria` (consumed via `data-i18n-aria`, fine);
  `ui.lang_switch_to_cs`, `ui.lang_switch_to_en`, `ui.verbose_on` (swapped in by JS, fine);
  `ui.present`, `ui.online_version`, `ui.toggle_section` (unreachable in this data — no period
  currently ends in "present"); and **`ui.level_senior`, `ui.level_medior`, `ui.level_working`** —
  these three are the real gap, see **B6**.
- **Toggle:** clicking through to Czech sets `<html lang="cs">` and rewrites every `data-i18n`
  element. Of 363 leaf text nodes, 226 are unchanged — all verified by hand as proper nouns, company
  names, technology lists, tag chips, and 7 keyed strings that are legitimately identical in both
  languages (`Vojtěch Špaček`, `AI / LLM / MCP`, the three interests lines, the book-titles note).
  The only genuine non-switching strings are the three in **B6**.
- **JSON-LD:** both `application/ld+json` blocks parse as valid JSON.
  - Block 1, `@type: Person` — `jobTitle` = *"Senior C++ engineer — safety-critical embedded & HIL
    test automation | Linux/networking | agentic-AI (MCP) tooling"* (tracks `meta.headline`, not a
    hard-coded string); **`alumniOf` is absent**, which is correct. Keys: `@context`, `@type`,
    `address`, `email`, `jobTitle`, `knowsAbout`, `knowsLanguage`, `name`, `sameAs`, `telephone`,
    `url`.
  - Block 2, `@type: ResumeAction` — `name`, `description`, `url`. No `jobTitle`/`alumniOf`.

### 11. `pl-b2b` carries no automotive claim — PASS
`grep -ric "aspice\|autosar\|qnx\|iso 26262\|misra"` returns **0** for every one of: the extracted
text of all four PDFs, `data/cv.yaml`, all three variant overlays, all four templates, `index.html`
and `cv-3-page.md`. Verified in the rendered PDF, not only the YAML.

The `pl-b2b` overlay is a pure rendering overlay — it declares no content keys at all, only
`sections`, `emphasize_tags`, `experience_detail`, `page_budget` and `exclude`, so it is structurally
incapable of introducing a claim. Its safety-critical positioning is carried entirely by the
aerospace (Honeywell) and gas-controller (Resideo) material that already exists in `data/cv.yaml`.
The reasoning for every control is documented in the file's comments, including why `skills` was
dropped and why `ai`/`mcp` tags are deliberately not emphasised. This is the cleanest of the three
variants.

---

## Appendix: full link check

46 unique URLs in `data/cv.yaml`, followed with redirects, browser UA.

**Confirmed working (21):** calendly, discord, glama.ai server page + badge (both redirect to
`glama.ai/mcp/servers/sparesparrow/mcp-prompts`), mcp.aibase.com, mcpmarket.com, refactoring.guru,
signal.me, skywork.ai, sparesparrow.github.io/cv/, three audible.com titles, coursera.org
specialization, hackthebox.com, youtube playlist, x.com.

**Confirmed working out of band (23):** all 18 `github.com/sparesparrow/*` URLs plus the merged-PRs
query (403 through the proxy; verified via GitHub repo search and `raw.githubusercontent.com` —
every repo exists), `npmjs.com/package/@sparesparrow/mcp-prompts` (403 through the proxy;
`registry.npmjs.org` returns 200), `crates.io/crates/rust-network-mgr` (404 to curl; the crates.io
API confirms 7 published versions), `linkedin.com/in/sparesparrow` (999 — LinkedIn's standard
anti-bot response).

**Dead (3):** see **B2**.
**Unverified (2):** mcphub.com, pulsemcp.com — see **B2**.

Content spot-check of the directory pages that returned 200: Glama (*"MCP Prompts Server by
sparesparrow"*), MCP Market (*"Prompts Server"*), AIBASE (*"Prompt Manager MCP Server"*) and Skywork
(*"Project Orchestrator MCP Server"*) all show real listings for his servers. MagicSlides does not —
it is the soft 404 in B2.
