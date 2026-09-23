// The export dialog, and the notification that replaces it.
//
// Pressing "Write the PDF" closes the dialog straight away and hands the job
// to a notification: "Exporting… 40%" while the server works, then "Batch
// exported" with Download and Open on the same line. The progress is real —
// the server counts each card drawn — so it tells you something a spinner
// cannot.
//
// Everything it shows about sheets, cards-per-sheet and output formats comes
// from /api/meta, so the count it predicts is the count the server produces
// and the menu lists exactly what the server can write. A format added in
// dixitgen.export.formats appears here with no edit to this file.
//
// Sheets versus images
// --------------------
// Only the A4 output lays cards on paper, so only it has a duplex pass and a
// printer to calibrate. Those two fieldsets are hidden for an image export
// rather than disabled: a control that cannot apply is noise, and leaving it
// visible invites the question of what it would have done.
//
// The calibration offset lives here because it is the thing you re-enter after
// holding a test print up to the light — see docs/PRINTING.md. It is
// deliberately not remembered by the browser: it belongs to a printer and a
// paper path, not to a browser profile.

import { api } from "./api.js";
import { $, clear, el } from "./dom.js";
import { dismiss, fail, notify, update } from "./toast.js";
import { selectedCards, state } from "./state.js";

//: How often to ask the server how far it has got. Fast enough to feel live,
//: slow enough not to flood a local server during a long batch.
const POLL_MS = 250;

function sheetsFor(count) {
  const perSheet = state.meta?.sheet?.cards_per_sheet || 0;
  return perSheet ? Math.ceil(count / perSheet) : 0;
}

function formats() {
  return state.meta?.formats || [];
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function flipOptions(selectedId) {
  const flips = state.meta?.flips || [];
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

// What the chosen format will produce, in the units that format thinks in:
// sheets of paper for the PDF, files in an archive for the image exports.
function summaryFor(format, count, hasBack) {
  if (!format) return [`${plural(count, "card")} selected`];

  if (format.uses_duplex) {
    const perSheet = state.meta.sheet.cards_per_sheet;
    const sheets = sheetsFor(count);
    const lastSheet = count % perSheet || perSheet;
    return [
      `${plural(count, "card")} → ${plural(sheets, "sheet")} of ${
        state.meta.paper.label
      }`,
      lastSheet !== perSheet
        ? el(
            "span",
            { class: "note" },
            ` — the last sheet carries ${lastSheet} of ${perSheet}, and backs print only where a card does.`
          )
        : null,
    ];
  }

  const files = count + (hasBack ? 1 : 0);
  return [
    `${plural(count, "card")} → ${plural(files, "image file")} in one .zip`,
    hasBack
      ? el("span", { class: "note" }, " — one shared back file for the deck.")
      : null,
  ];
}

export function openExport() {
  const dialog = $("#export-dialog");
  const body = $("#export-body");
  if (!dialog || !body) return;

  const cards = selectedCards();
  if (!cards.length) {
    notify("Select some cards first.", { kind: "warn" });
    return;
  }

  const nameInput = el("input", { type: "text", id: "export-name", value: "batch" });
  const offsetX = el("input", { type: "number", id: "offset-x", step: "0.1", value: "0" });
  const offsetY = el("input", { type: "number", id: "offset-y", step: "0.1", value: "0" });
  const backSelect = el(
    "select",
    { id: "export-back", onchange: () => sync() },
    el("option", { value: "" }, "No back (fronts only)"),
    ...state.backs.map((back) =>
      el("option", { value: String(back.id) }, back.name || `#${back.id}`)
    )
  );
  const formatSelect = el(
    "select",
    { id: "export-format", onchange: () => sync() },
    ...formats().map((format) => el("option", { value: format.id }, format.label))
  );

  const summary = el("p", { class: "export-summary" });
  const formatNote = el("p", { class: "note" });
  const duplexFields = el(
    "fieldset",
    { class: "flips" },
    el("legend", {}, "Duplex mode"),
    ...flipOptions("long-edge")
  );
  const offsetFields = el(
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
  );

  // Re-read from the live controls rather than from a captured value: the
  // back select changes the file count, and the format changes everything.
  function sync() {
    const format = formats().find((one) => one.id === formatSelect.value);
    const onPaper = Boolean(format && format.uses_duplex);

    formatNote.textContent = format ? format.detail : "";
    duplexFields.hidden = !onPaper;
    offsetFields.hidden = !onPaper;

    // The button says what it will actually do; "Write the PDF" over a zip
    // export is a small lie that costs a support question.
    const run = $("#export-run");
    if (run) run.textContent = onPaper ? "Write the PDF" : "Write the images";

    clear(summary);
    for (const part of summaryFor(format, cards.length, Boolean(backSelect.value))) {
      if (part === null || part === undefined) continue;
      summary.append(part.nodeType ? part : document.createTextNode(String(part)));
    }
  }

  clear(body);
  body.append(
    summary,
    el("label", {}, "Output", formatSelect),
    formatNote,
    el("label", {}, "File name", nameInput),
    el("label", {}, "Back image", backSelect),
    duplexFields,
    offsetFields
  );
  sync();

  dialog.hidden = false;
  dialog.dataset.open = "true";
}

export function closeExport() {
  const dialog = $("#export-dialog");
  if (!dialog) return;
  dialog.hidden = true;
  delete dialog.dataset.open;
}

function finish(toastId, status) {
  const files = status.files || [];
  const primary = files[0];
  const actions = [];
  if (primary) {
    actions.push({
      label: "Download",
      href: primary.download_url || primary.url,
      download: primary.name,
    });
    // A zip has nothing to show inline — the browser would download it anyway,
    // from a button that claims it will open something.
    if (!primary.name.toLowerCase().endsWith(".zip")) {
      actions.push({ label: "Open", href: primary.url, newTab: true });
    }
  }

  const extras = files.length > 1 ? ` · ${files.length} files` : "";
  const warned = (status.warnings || []).length;
  const made = status.sheets
    ? `${plural(status.sheets, "sheet")}, ${plural(status.cards, "card")} (${status.flip})`
    : `${plural(status.cards, "card")}, ${plural(status.images || 0, "image")}`;

  // The count of resolution warnings stays; the warnings themselves do not.
  // One line per soft card ran to thousands of characters on a real deck and
  // buried the Download button under a wall of text that said the same thing
  // the grid's "soft" badges already say, card by card, before you export.
  update(toastId, {
    kind: "success",
    text: "Batch exported",
    percent: undefined,
    detail:
      `${made}${extras} · in out/` +
      (warned ? ` · ${warned} resolution warning${warned === 1 ? "" : "s"}` : ""),
    actions,
  });
}

export async function runExport() {
  const checked = document.querySelector('input[name="flip"]:checked');
  const payload = {
    card_ids: state.selection,
    back_id: $("#export-back").value ? Number($("#export-back").value) : null,
    format: $("#export-format").value,
    flip: checked ? checked.value : "long-edge",
    name: $("#export-name").value || "batch",
    offset_mm: {
      x: Number($("#offset-x").value || 0),
      y: Number($("#offset-y").value || 0),
    },
  };

  // Out of the way immediately: the work happens on the server and the
  // notification carries it from here.
  closeExport();
  const toastId = notify("Exporting…", { kind: "progress", percent: 0 });

  let job;
  try {
    job = await api.startExport(payload);
  } catch (error) {
    dismiss(toastId);
    fail(error);
    return;
  }

  const poll = async () => {
    let status;
    try {
      status = await api.exportStatus(job.job_id);
    } catch (error) {
      dismiss(toastId);
      fail(error);
      return;
    }

    if (status.state === "running") {
      update(toastId, {
        text: "Exporting…",
        percent: status.percent || 0,
        detail: `${status.done} of ${status.total} cards drawn`,
      });
      setTimeout(poll, POLL_MS);
      return;
    }
    if (status.state === "error") {
      dismiss(toastId);
      fail(new Error(status.error || "the export failed"));
      return;
    }
    finish(toastId, status);
  };

  setTimeout(poll, POLL_MS);
}
