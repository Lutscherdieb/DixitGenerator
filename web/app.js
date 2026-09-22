// The overview client.  No build step: plain ES modules, loaded directly.
//
// Rule this file lives under: it never types a print measurement.  Every
// number comes from /api/meta, which serves dixitgen.spec.  The check in
// tools/check_geometry_literals.py scans web/ for unit-anchored literals and
// fails the build if one appears here.

const $ = (sel) => document.querySelector(sel);

async function fetchMeta() {
  const response = await fetch("/api/meta");
  if (!response.ok) {
    throw new Error(`/api/meta returned ${response.status}`);
  }
  return response.json();
}

function row(term, value) {
  return `<dt>${term}</dt><dd>${value}</dd>`;
}

function render(meta) {
  const { card, paper, sheet, flips } = meta;
  const mm = (n) => `${n} mm`;

  $("#spec").innerHTML = [
    row("Card", `${card.label} &mdash; ${mm(card.trim_w_mm)} &times; ${mm(card.trim_h_mm)}`),
    row("At print resolution", `${card.trim_w_px} &times; ${card.trim_h_px} px at ${card.dpi} DPI`),
    row("Aspect", card.aspect.toFixed(4).replace(/0+$/, "")),
    row("Paper", paper.label),
    row("Grid", `${sheet.cols} &times; ${sheet.rows} &mdash; ${sheet.cards_per_sheet} cards per sheet`),
    row("Block", `${mm(sheet.block_w_mm)} &times; ${mm(sheet.block_h_mm)}`),
    row("Margins", `${mm(sheet.margin_x_mm)} left/right, ${mm(sheet.margin_y_mm)} top/bottom`),
    row("Outer bleed", `${mm(sheet.outer_bleed_mm)} on the block's outer edges only`),
    row(
      "Duplex modes",
      flips
        .map((f) => `${f.id}${f.back_rotation_deg ? ` (back turned ${f.back_rotation_deg}&deg;)` : ""}`)
        .join(", ")
    ),
    row("Version", meta.version),
  ].join("");
}

function renderError(err) {
  $("#spec").innerHTML =
    `<dd class="error">Could not read /api/meta: ${err.message}</dd>`;
}

fetchMeta().then(render).catch(renderError);
