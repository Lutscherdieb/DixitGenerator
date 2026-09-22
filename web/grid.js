// The card grid.
//
// A tile shows the *print crop* -- the server's thumbnail is already cropped
// to the card's aspect at the card's focus -- so what you pick in the grid is
// what the guillotine gives you.
//
// Click toggles selection; shift-click extends a range; the pencil opens the
// editor. Selection and editing are deliberately different gestures: a batch
// is built by clicking many cards, and opening an editor on every click would
// make that unusable.

import { $, clear, el } from "./dom.js";
import { isSelected, selectRange, state, toggle } from "./state.js";

function tile(card, onEdit) {
  const selectedAt = state.selection.indexOf(card.id);
  const node = el(
    "figure",
    {
      class: `tile${isSelected(card.id) ? " is-selected" : ""}${
        card.soft ? " is-soft" : ""
      }`,
      dataset: { id: String(card.id) },
      tabindex: "0",
      role: "button",
      "aria-pressed": String(isSelected(card.id)),
      "aria-label": card.name || `card ${card.id}`,
      onclick: (event) => {
        if (event.shiftKey) selectRange(card.id);
        else toggle(card.id);
      },
      onkeydown: (event) => {
        if (event.key === " " || event.key === "Enter") {
          event.preventDefault();
          toggle(card.id);
        }
      },
    },
    el("img", {
      class: "tile-art",
      src: card.thumb_url,
      alt: card.name || "",
      loading: "lazy",
      draggable: "false",
    }),
    selectedAt === -1
      ? null
      : el("span", { class: "tile-order" }, String(selectedAt + 1)),
    card.soft
      ? el(
          "span",
          {
            class: "tile-soft",
            title: `${card.src_w}x${card.src_h} is below the resolution this prints at — it will look soft`,
          },
          "soft"
        )
      : null,
    el(
      "button",
      {
        class: "tile-edit",
        type: "button",
        title: "Edit name, tags and crop",
        "aria-label": `edit ${card.name || card.id}`,
        onclick: (event) => {
          event.stopPropagation();
          onEdit(card);
        },
      },
      "✎"
    ),
    el("figcaption", { class: "tile-name" }, card.name || `#${card.id}`)
  );
  return node;
}

export function renderGrid(onEdit) {
  const grid = $("#grid");
  if (!grid) return;
  clear(grid);

  if (!state.cards.length) {
    grid.append(
      el(
        "p",
        { class: "empty" },
        state.filter.tag || state.filter.q
          ? "No cards match that filter."
          : "No cards yet — drop some images anywhere on this page."
      )
    );
    return;
  }

  for (const card of state.cards) grid.append(tile(card, onEdit));
}
