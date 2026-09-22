// The export dialog, and the notification that replaces it.
//
// Pressing "Write the PDF" closes the dialog straight away and hands the job
// to a notification: "Exporting… 40%" while the server works, then "Batch
// exported" with Download and Open on the same line. The progress is real —
// the server counts each card drawn — so it tells you something a spinner
// cannot.
//
// Everything it shows about sheets and cards-per-sheet comes from /api/meta,
// so the count it predicts is the count the server produces.
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

export function openExport() {
  const dialog = $("#export-dialog");
  const body = $("#export-body");
  if (!dialog || !body) return;

  const cards = selectedCards();
  if (!cards.length) {
    notify("Select some cards first.", { kind: "warn" });
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
    )
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
    actions.push({ label: "Open", href: primary.url, newTab: true });
  }

  const extras = files.length > 1 ? ` · ${files.length} files` : "";
  const warned = (status.warnings || []).length;
  update(toastId, {
    kind: "success",
    text: "Batch exported",
    percent: undefined,
    detail:
      `${status.sheets} sheet${status.sheets === 1 ? "" : "s"}, ` +
      `${status.cards} card${status.cards === 1 ? "" : "s"} (${status.flip})` +
      `${extras} · in out/` +
      (warned ? ` · ${warned} resolution warning${warned === 1 ? "" : "s"}` : ""),
    actions,
  });

  if (warned) {
    notify(`${warned} card${warned === 1 ? "" : "s"} will print soft`, {
      kind: "warn",
      detail: status.warnings.join(" · "),
    });
  }
}

export async function runExport() {
  const checked = document.querySelector('input[name="flip"]:checked');
  const payload = {
    card_ids: state.selection,
    back_id: $("#export-back").value ? Number($("#export-back").value) : null,
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
