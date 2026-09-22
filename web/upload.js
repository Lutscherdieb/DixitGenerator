// Uploading: drag a file, a selection, or a whole folder anywhere on the page.
//
// A drop can carry one bad file among forty good ones. The server skips the
// bad one and reports it by name rather than failing the batch -- losing
// thirty-nine good uploads to one stray .txt is the kind of thing that makes
// people stop using a tool.

import { api } from "./api.js";
import { $ } from "./dom.js";
import { fail, say } from "./toast.js";
import { state } from "./state.js";

const IMAGE = /^image\//;

function imagesOnly(fileList) {
  return [...fileList].filter((file) => IMAGE.test(file.type) || !file.type);
}

async function send(files, reload) {
  const images = imagesOnly(files);
  if (!images.length) {
    say("Nothing to upload — those were not images.", "error");
    return;
  }
  say(`Uploading ${images.length} file${images.length === 1 ? "" : "s"}…`);
  try {
    const result = await api.uploadCards(images, state.uploadTag);
    const added = result.created.length;
    const skipped = result.skipped.length;
    say(
      `Added ${added} card${added === 1 ? "" : "s"}` +
        (state.uploadTag ? ` tagged “${state.uploadTag}”` : "") +
        (skipped ? ` · skipped ${skipped}: ${result.skipped.map((s) => s.name).join(", ")}` : ""),
      skipped ? "warn" : "info"
    );
    await reload();
  } catch (error) {
    fail(error);
  }
}

export function wireUpload(reload) {
  const zone = document.body;
  const picker = $("#file-input");
  const tagInput = $("#upload-tag");

  if (tagInput) {
    tagInput.addEventListener("input", () => {
      state.uploadTag = tagInput.value.trim();
    });
  }

  if (picker) {
    picker.addEventListener("change", async () => {
      if (picker.files && picker.files.length) await send(picker.files, reload);
      picker.value = "";
    });
  }

  let depth = 0;
  zone.addEventListener("dragenter", (event) => {
    event.preventDefault();
    depth += 1;
    zone.classList.add("is-dropping");
  });
  zone.addEventListener("dragover", (event) => event.preventDefault());
  zone.addEventListener("dragleave", () => {
    depth = Math.max(0, depth - 1);
    if (!depth) zone.classList.remove("is-dropping");
  });
  zone.addEventListener("drop", async (event) => {
    event.preventDefault();
    depth = 0;
    zone.classList.remove("is-dropping");
    if (event.dataTransfer && event.dataTransfer.files.length) {
      await send(event.dataTransfer.files, reload);
    }
  });
}
