// Wiring. This module is the only one that knows about all the others, which
// keeps the rest acyclic:
//     api <- state <- {grid, editor, upload, backs, exporter} <- app
//
// It types no print measurement. Every number shown comes from /api/meta,
// which serves dixitgen.spec; tools/check_geometry_literals.py scans web/ and
// fails the build if a literal appears here.

import { api } from "./api.js";
import { $, el } from "./dom.js";
import { fail } from "./toast.js";
import { renderBacks, wireBackUpload } from "./backs.js";
import { closeEditor, openEditor } from "./editor.js";
import { closeExport, openExport, runExport } from "./exporter.js";
import { renderGrid } from "./grid.js";
import { clearSelection, emit, selectAll, state, subscribe } from "./state.js";
import { wireUpload } from "./upload.js";

async function reload() {
  const [cards, tags, backs] = await Promise.all([
    api.listCards(state.filter),
    api.listTags(),
    api.listBacks(),
  ]);
  state.cards = cards.cards;
  state.tags = tags.tags;
  state.backs = backs.backs;
  // Drop anything deleted or filtered away, so an export can never carry an id
  // the grid is no longer showing.
  const visible = new Set(state.cards.map((card) => card.id));
  state.selection = state.selection.filter((id) => visible.has(id));
  emit();
}

function renderToolbar() {
  const tagSelect = $("#filter-tag");
  if (tagSelect) {
    const current = state.filter.tag;
    tagSelect.innerHTML = "";
    tagSelect.append(el("option", { value: "" }, "All tags"));
    for (const tag of state.tags) {
      tagSelect.append(
        el(
          "option",
          { value: tag.name, selected: tag.name === current },
          `${tag.name} (${tag.count})`
        )
      );
    }
  }

  const count = $("#selection-count");
  if (count) {
    count.textContent = state.selection.length
      ? `${state.selection.length} selected`
      : `${state.cards.length} card${state.cards.length === 1 ? "" : "s"}`;
  }
  const exportButton = $("#export-open");
  if (exportButton) exportButton.disabled = state.selection.length === 0;
}

function renderSpecLine() {
  const line = $("#spec-line");
  if (!line || !state.meta) return;
  const { card, paper, sheet } = state.meta;
  line.textContent =
    `${card.label} · ${paper.label} · ${sheet.cols}×${sheet.rows} = ` +
    `${sheet.cards_per_sheet} per sheet · ${card.dpi} DPI`;
}

function renderAll() {
  renderToolbar();
  renderGrid((card) =>
    openEditor(card, { kind: "cards", onSaved: reload, onDeleted: reload })
  );
  renderBacks(reload, (back) =>
    openEditor(back, { kind: "backs", onSaved: reload, onDeleted: reload })
  );
}

function wireToolbar() {
  const search = $("#filter-q");
  let timer = null;
  if (search) {
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        state.filter.q = search.value.trim();
        try {
          await reload();
        } catch (error) {
          fail(error);
        }
      }, 200);
    });
  }

  const tagSelect = $("#filter-tag");
  if (tagSelect) {
    tagSelect.addEventListener("change", async () => {
      state.filter.tag = tagSelect.value;
      try {
        await reload();
      } catch (error) {
        fail(error);
      }
    });
  }

  const on = (id, event, handler) => {
    const node = $(id);
    if (node) node.addEventListener(event, handler);
  };
  on("#select-all", "click", selectAll);
  on("#select-none", "click", clearSelection);
  on("#export-open", "click", openExport);
  on("#export-close", "click", closeExport);
  on("#export-run", "click", runExport);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeExport();
    closeEditor();
  });
}

async function main() {
  subscribe(renderAll);
  wireToolbar();
  wireUpload(reload);
  wireBackUpload(reload);

  try {
    state.meta = await api.meta();
    renderSpecLine();
    await reload();
    // An explicit readiness flag, for tests and for anyone watching the page
    // wake up. Waiting on an element instead proves nothing: #spec-line and
    // #grid both exist in the static HTML before a single byte of data has
    // arrived, so a check that waits for them races the app and passes or
    // fails by luck.
    document.body.dataset.ready = "true";
  } catch (error) {
    document.body.dataset.ready = "error";
    fail(error);
  }
}

main();
