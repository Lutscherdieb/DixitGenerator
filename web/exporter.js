// The export dialog.
//
// Everything it shows about sheets and cards-per-sheet comes from /api/meta,
// so the count it predicts is the count the server will produce.
//
// The calibration offset lives here because it is the thing you re-enter after
// holding a test print up to the light -- see docs/PRINTING.md. It is not
// persisted by the browser on purpose: it belongs to a printer and a paper
// path, not to a browser profile, and docs/PRINTING.md puts it in the
// gitignored printer.local.json.

import { api } from "./api.js";
import { $, clear, el, fail, say } from "./dom.js";
import { selectedCards, state } from "./state.js";

function sheetsFor(count) {
  const perSheet = state.meta && state.meta.sheet ? state.meta.sheet.cards_per_sheet : 0;
  return perSheet ? Math.ceil(count / perSheet) : 0;
}

function flipOptions(selectedId) {
  const flips = (state.meta && state.meta.flips) || [];
  const label = {
    "long-edge": "Auto duplex — flip on long edge (usual default)",
    "short-edge": "Auto duplex — flip on short edge (back turned 180°)",
    manual: "Manual — two files, fronts and backs",
  };
  return flips.map((flip) =>
    el(
      "label",
      { class: "radio" },
      el("input", {
        type: "radio",
        name: "flip",
        value: flip.id,
        checked: flip.id === selectedId,
      }),
      label[flip.id] || flip.id
    )
  );
}

export function openExport() {
  const dialog = $("#export-dialog");
  const body = $("#export-body");
  if (!dialog || !body) return;

  const cards = selectedCards();
  if (!cards.length) {
    say("Select some cards first.", "warn");
    return;
  }

  const perSheet = state.meta.sheet.cards_per_sheet;
  const sheets = sheetsFor(cards.length);
  const lastSheet = cards.length % perSheet || perSheet;
  const soft = cards.filter((card) => card.soft);

  const nameInput = el("input", { type: "text", id: "export-name", value: "batch" });
  const offsetX = el("input", { type: "number", id: "offset-x", step: "0.1", value: "0" });
  const offsetY = el("input", { type: "number", id: "offset-y", step: "0.1", value: "0" });
  const backSelect = el(
    "select",
    { id: "export-back" },
    el("option", { value: "" }, "No back (fronts only)"),
    ...state.backs.map((back) =>
      el("option", { value: String(back.id) }, back.name || `#${back.id}`)
    )
  );

  clear(body);
  body.append(
    el(
      "p",
      { class: "export-summary" },
      `${cards.length} card${cards.length === 1 ? "" : "s"} → ${sheets} sheet${
        sheets === 1 ? "" : "s"
      } of ${state.meta.paper.label}`,
      lastSheet !== perSheet
        ? el(
            "span",
            { class: "note" },
            ` — the last sheet carries ${lastSheet} of ${perSheet}, and backs print only where a card does.`
          )
        : null
    ),
    soft.length
      ? el(
          "p",
          { class: "warn-box" },
          `${soft.length} of these will print soft: ${soft
            .map((card) => card.name || `#${card.id}`)
            .join(", ")}. Exporting anyway is fine — it is your call.`
        )
      : null,
    el("label", {}, "File name", nameInput),
    el("label", {}, "Back image", backSelect),
    el("fieldset", { class: "flips" }, el("legend", {}, "Duplex mode"), ...flipOptions("long-edge")),
    el(
      "fieldset",
      { class: "offsets" },
      el("legend", {}, "Printer calibration offset (mm)"),
      el(
        "p",
        { class: "note" },
        "Leave at zero until you have measured yours — print a test sheet, hold it to the light, and read the gap between the front and back crop marks. See docs/PRINTING.md."
      ),
      el("label", {}, "x", offsetX),
      el("label", {}, "y", offsetY)
    ),
    el("div", { id: "export-result" })
  );

  dialog.hidden = false;
  dialog.dataset.open = "true";
}

export function closeExport() {
  const dialog = $("#export-dialog");
  if (!dialog) return;
  dialog.hidden = true;
  delete dialog.dataset.open;
}

export async function runExport() {
  const button = $("#export-run");
  const result = $("#export-result");
  const checked = document.querySelector('input[name="flip"]:checked');
  const backValue = $("#export-back").value;

  const payload = {
    card_ids: state.selection,
    back_id: backValue ? Number(backValue) : null,
    flip: checked ? checked.value : "long-edge",
    name: $("#export-name").value || "batch",
    offset_mm: {
      x: Number($("#offset-x").value || 0),
      y: Number($("#offset-y").value || 0),
    },
  };

  button.disabled = true;
  say("Writing the PDF…");
  try {
    const response = await api.exportBatch(payload);
    clear(result);
    result.append(
      el(
        "p",
        { class: "ok" },
        `Wrote ${response.sheets} sheet${response.sheets === 1 ? "" : "s"} for ${
          response.cards
        } card${response.cards === 1 ? "" : "s"} (${response.flip}).`
      ),
      el(
        "ul",
        { class: "files" },
        ...response.files.map((file) =>
          el(
            "li",
            {},
            el("a", { href: file.url, download: file.name }, file.name),
            ` — ${(file.size / 1024).toFixed(0)} KB, in out/`
          )
        )
      ),
      response.warnings.length
        ? el(
            "details",
            { class: "warn-box" },
            el("summary", {}, `${response.warnings.length} resolution warning(s)`),
            el("ul", {}, ...response.warnings.map((w) => el("li", {}, w)))
          )
        : null,
      el(
        "p",
        { class: "note" },
        "Print at 100% / “Actual size”, and match your printer's duplex setting to the mode above. docs/PRINTING.md has the rest."
      )
    );
    say("Export written.");
  } catch (error) {
    fail(error);
  } finally {
    button.disabled = false;
  }
}
