![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)
![Last Updated](https://img.shields.io/github/last-commit/sparesparrow/cv)
![View on GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-live-brightgreen)

# Vojtěch Špaček – Resume / CV

Senior C++ engineer — safety-critical embedded and HIL test automation, Linux and
networking, agentic-AI (MCP) tooling.

## Reading it

- **[Live CV](https://sparesparrow.github.io/cv/)** — the interactive page, English and Czech.
- `dist/vs-cv-master.pdf` — the full CV as a PDF.
- Market-tailored versions, each two pages:
  - `dist/vs-cv-cz-contractor.pdf` — Czech contractor market
  - `dist/vs-cv-pl-b2b.pdf` — Polish B2B market
  - `dist/vs-cv-ch.pdf` — Swiss application dossier

## Editing it

**`data/cv.yaml` is the single source of truth. Everything else is generated.**

`index.html`, `cv-3-page.md` and every PDF are build outputs and carry a
`DO NOT EDIT` header. Editing them directly is how this repo previously ended up
with an HTML CV and a Markdown CV that had silently drifted apart, each holding
facts the other lacked. Change the data, then rebuild:

```sh
python3 build.py --all                    # index.html, cv-3-page.md, master PDF
python3 build.py --variant cz-contractor  # one variant PDF
python3 build.py --check                  # every assertion, writes nothing
python3 build.py --list-variants
```

Requires Python 3.11+, `pyyaml`, `jinja2`, and a Chromium binary for PDF output.

Market variants are overlays in `data/variants/` — they select and re-order what
`data/cv.yaml` already says. They hold no prose of their own, so a fact can never
disagree between two versions of the CV.

## What the build enforces

`build.py --check` fails, rather than warns, if any of these break:

- experience is reverse-chronological and every entry carries a start date
- every experience entry actually reaches the rendered output
- nothing in any output states or implies an awarded degree
- no output leaks the `TODO(user)` marker used for facts nobody has supplied yet
- each variant PDF stays within its declared page budget

Run it before pushing. Output is deterministic: a second build is byte-identical.

## Contributing

Corrections are welcome — typos, accessibility, broken links. Please edit
`data/cv.yaml` or the templates and include the rebuilt output, rather than
editing `index.html` directly.

## License

MIT.
