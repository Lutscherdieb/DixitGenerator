// The editor: name, notes, tags, and the crop nudge.
//
// It serves **both** cards and backs. A back is an image with a name and a
// crop focus, exactly like a card, so it gets the same re-framing tool; it
// simply has no tags and no notes. `kind` ("cards" or "backs") is the only
// difference, and it only picks the API path.
//
// The crop window is the card's shape, showing the FULL-resolution original
// scaled to cover it. Dragging the picture moves the crop, exactly as it will
// be cropped for print.
//
// The maths, once:
//   scale  = max(winW / imgW, winH / imgH)        -- cover, never letterbox
//   ox     = imgW * scale - winW                  -- horizontal slack, >= 0
//   focusX = (how far the image's left edge sits left of the window) / ox
// so focusX 0 shows the source's left edge and 1 its right. When ox is 0 the
// source is already the card's shape and there is nothing to nudge -- that is
// correct, not a bug, and the UI says so rather than looking broken.

import { api } from "./api.js";
import { $, clear, el } from "./dom.js";
import { fail, say } from "./toast.js";
import { state } from "./state.js";

let dragging = null;

const LABELS = {
  cards: { noun: "card", deleteWarning: "This removes the image from the library." },
  backs: { noun: "back", deleteWarning: "This removes the back from the shelf." },
};

function cardAspect() {
  // From /api/meta -- never a literal in this file.
  const card = state.meta && state.meta.card;
  return card ? card.trim_w_mm / card.trim_h_mm : 2 / 3;
}

function layout(win, img) {
  const winW = win.clientWidth;
  const winH = win.clientHeight;
  const imgW = img.naturalWidth;
  const imgH = img.naturalHeight;
  if (!winW || !winH || !imgW || !imgH) return null;
  const scale = Math.max(winW / imgW, winH / imgH);
  return {
    winW,
    winH,
    drawW: imgW * scale,
    drawH: imgH * scale,
    ox: Math.max(0, imgW * scale - winW),
    oy: Math.max(0, imgH * scale - winH),
  };
}

function place(win, img, focus) {
  const box = layout(win, img);
  if (!box) return;
  img.style.width = `${box.drawW}px`;
  img.style.height = `${box.drawH}px`;
  img.style.left = `${-focus.x * box.ox}px`;
  img.style.top = `${-focus.y * box.oy}px`;

  const hint = $("#crop-hint");
  if (hint) {
    const free = box.ox > 0.5 || box.oy > 0.5;
    hint.textContent = free
      ? "Drag the picture to choose what the card keeps."
      : "This image is already the card's shape — there is nothing to crop.";
    hint.dataset.free = String(free);
  }
  const read = $("#crop-readout");
  if (read) read.textContent = `${focus.x.toFixed(2)}, ${focus.y.toFixed(2)}`;
}

const clamp = (value) => Math.min(1, Math.max(0, value));

function startDrag(event, win, img, focus) {
  const box = layout(win, img);
  if (!box || (box.ox <= 0.5 && box.oy <= 0.5)) return;
  win.setPointerCapture(event.pointerId);
  dragging = {
    startX: event.clientX,
    startY: event.clientY,
    fromX: focus.x,
    fromY: focus.y,
    box,
  };
}

function moveDrag(event, win, img, focus) {
  if (!dragging) return;
  const { box } = dragging;
  // Dragging right reveals more of the source's left, so focus decreases.
  if (box.ox > 0) {
    focus.x = clamp(dragging.fromX - (event.clientX - dragging.startX) / box.ox);
  }
  if (box.oy > 0) {
    focus.y = clamp(dragging.fromY - (event.clientY - dragging.startY) / box.oy);
  }
  place(win, img, focus);
}

export function closeEditor() {
  state.editingId = null;
  state.editingKind = null;
  const panel = $("#editor");
  if (panel) {
    panel.hidden = true;
    clear(panel);
  }
}

export function openEditor(item, { kind = "cards", onSaved, onDeleted } = {}) {
  const panel = $("#editor");
  if (!panel) return;
  const words = LABELS[kind] || LABELS.cards;
  state.editingId = item.id;
  state.editingKind = kind;
  const focus = { x: item.focus.x, y: item.focus.y };

  const img = el("img", {
    id: "crop-img",
    src: item.image_url,
    alt: item.name || "",
    draggable: "false",
  });
  const win = el(
    "div",
    {
      id: "crop-window",
      style: `aspect-ratio:${cardAspect()}`,
      onpointerdown: (event) => startDrag(event, win, img, focus),
      onpointermove: (event) => moveDrag(event, win, img, focus),
      onpointerup: () => {
        dragging = null;
      },
      onpointercancel: () => {
        dragging = null;
      },
    },
    img
  );

  const nameInput = el("input", {
    id: "edit-name",
    type: "text",
    value: item.name || "",
  });
  const notesInput =
    kind === "cards"
      ? el("textarea", { id: "edit-notes", rows: "3" }, item.notes || "")
      : null;
  const tagsInput =
    kind === "cards"
      ? el("input", {
          id: "edit-tags",
          type: "text",
          value: (item.tags || []).join(", "),
          placeholder: "comma separated",
        })
      : null;

  const save = async () => {
    try {
      const fields = { name: nameInput.value };
      if (kind === "cards") {
        fields.notes = notesInput.value;
        fields.tags = tagsInput.value
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean);
      }
      await api.update(kind, item.id, fields);
      if (focus.x !== item.focus.x || focus.y !== item.focus.y) {
        await api.setFocus(kind, item.id, focus.x, focus.y);
      }
      say(`Saved “${nameInput.value || item.id}”.`);
      closeEditor();
      if (onSaved) await onSaved();
    } catch (error) {
      fail(error);
    }
  };

  const remove = async () => {
    const label = item.name || `${words.noun} ${item.id}`;
    if (
      !window.confirm(
        `Delete “${label}” permanently?\n\n${words.deleteWarning} There is no ` +
          "undo, and the database holds the only copy."
      )
    ) {
      return;
    }
    try {
      await api.remove(kind, item.id);
      say(`Deleted “${label}”.`);
      closeEditor();
      if (onDeleted) await onDeleted();
    } catch (error) {
      fail(error);
    }
  };

  clear(panel);
  panel.hidden = false;
  panel.append(
    el(
      "div",
      { class: "editor-crop" },
      win,
      el("p", { id: "crop-hint", class: "note" }),
      el(
        "p",
        { class: "note" },
        "focus ",
        el("code", { id: "crop-readout" }, "0.50, 0.50"),
        " · source ",
        `${item.src_w}×${item.src_h}`,
        item.soft ? " · will print soft" : ""
      ),
      el(
        "button",
        {
          type: "button",
          class: "ghost",
          onclick: () => {
            focus.x = 0.5;
            focus.y = 0.5;
            place(win, img, focus);
          },
        },
        "Centre"
      )
    ),
    el(
      "div",
      { class: "editor-fields" },
      el("h3", { class: "editor-title" }, `Editing ${words.noun}`),
      el("label", {}, "Name", nameInput),
      tagsInput ? el("label", {}, "Tags", tagsInput) : null,
      notesInput ? el("label", {}, "Notes", notesInput) : null,
      el(
        "div",
        { class: "editor-actions" },
        el(
          "button",
          { type: "button", class: "primary", id: "edit-save", onclick: save },
          "Save"
        ),
        el("button", { type: "button", class: "ghost", onclick: closeEditor }, "Cancel"),
        el(
          "button",
          { type: "button", class: "danger", id: "edit-delete", onclick: remove },
          "Delete"
        )
      )
    )
  );

  // The image must be measurable before it can be placed.
  if (img.complete) place(win, img, focus);
  else img.addEventListener("load", () => place(win, img, focus), { once: true });
  window.addEventListener("resize", () => place(win, img, focus));
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
