# Gantt Studio — JS tests

These tests run **outside** Odoo, under plain Node, so they can be executed
without booting a database. They exercise the *pure* JS layers of the module:

- `gantt_studio_utils.js` (date math, parsing, geometry, palette, text-fit)
- `gantt_studio_renderer.js` (dirty flags + virtual-grid slicing, with OWL
  and `@web/core/*` stubbed)

The OWL Component itself is NOT instantiated (that would require a browser
DOM and the full `@web/*` runtime). Instead, an instance is constructed via
`Object.create(GanttStudioRenderer.prototype)` so we can exercise its
state-machine methods (`_diffProps`, `_beforeRender`, `_sliceVisibleRows`)
deterministically.

## Run

```bash
cd gantt_studio/tests/js
node test_utils.mjs
node test_renderer.mjs
# or both:
./run_all.sh
```

`@xmldom/xmldom` is required for `test_utils.mjs` (used to parse arch XML
strings in the pure parseGanttStudioArch path). It is installed once in
`/tmp` and shared across runs.

## Why not Odoo's hoot / QUnit runner?

The hoot runner in Odoo 18 requires the asset bundle and a browser-like
runtime. These tests are deliberately **harness-free** so:

1. They run fast (cold start < 1s).
2. They don't need the database to exist.
3. They can be wired into CI without a Chrome installation.

For browser-level integration we still rely on manual testing in the actual
view + the Python `TransactionCase` suite under `../`.
