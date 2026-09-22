// The backs shelf.
//
// Separate from the card grid on purpose: a back is not a playable card, and
// picking one at export time should not mean hunting through two hundred
// fronts. The store enforces the same separation with its own table.

import { api } from "./api.js";
import { $, clear, el, fail, say } from "./dom.js";
import { state } from "./state.js";

export function renderBacks(reload) {
  const shelf = $("#backs");
  if (!shelf) return;
  clear(shelf);

  if (!state.backs.length) {
    shelf.append(
      el("p", { class: "empty" }, "No backs yet — add one to print double-sided.")
    );
    return;
  }

  for (const back of state.backs) {
    shelf.append(
      el(
        "figure",
        { class: "back-tile", dataset: { id: String(back.id) } },
        el("img", { src: back.thumb_url, alt: back.name || "", loading: "lazy" }),
        el("figcaption", {}, back.name || `#${back.id}`),
        el(
          "button",
          {
            type: "button",
            class: "tile-edit",
            title: "Delete this back",
            onclick: async () => {
              if (!window.confirm(`Delete the back “${back.name || back.id}”? There is no undo.`)) return;
              try {
                await api.deleteBack(back.id);
                say("Back deleted.");
                await reload();
              } catch (error) {
                fail(error);
              }
            },
          },
          "✕"
        )
      )
    );
  }
}

export function wireBackUpload(reload) {
  const picker = $("#back-input");
  if (!picker) return;
  picker.addEventListener("change", async () => {
    if (picker.files && picker.files.length) {
      try {
        const result = await api.uploadBacks(picker.files);
        say(`Added ${result.created.length} back${result.created.length === 1 ? "" : "s"}.`);
        await reload();
      } catch (error) {
        fail(error);
      }
    }
    picker.value = "";
  });
}
