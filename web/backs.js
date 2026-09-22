// The backs shelf.
//
// Separate from the card grid on purpose: a back is not a playable card, and
// picking one at export time should not mean hunting through two hundred
// fronts. The store enforces the same separation with its own table.

import { api } from "./api.js";
import { $, clear, el } from "./dom.js";
import { fail, say } from "./toast.js";
import { state } from "./state.js";

export function renderBacks(reload, onEdit) {
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
            title: "Rename this back and adjust its crop",
            "aria-label": `edit ${back.name || back.id}`,
            onclick: () => onEdit(back),
          },
          "✎"
        ),
        back.soft
          ? el(
              "span",
              {
                class: "tile-soft",
                title: `${back.src_w}x${back.src_h} is below the resolution this prints at`,
              },
              "soft"
            )
          : null
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
