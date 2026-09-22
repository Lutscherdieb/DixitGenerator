// Notifications, pinned to the top of the *viewport*.
//
// They stack, each one carries its own dismiss button, and the container has no
// box of its own — with nothing to show, the page is completely clear.
//
// A toast can be updated in place (`update`), which is how the export reports
// progress: one notification goes from "Exporting… 40%" to "Batch exported"
// with its Download and Open buttons, rather than piling up a new line per
// poll.

import { $, clear, el } from "./dom.js";

const KINDS = new Set(["info", "progress", "success", "warn", "error"]);

//: Only quiet, purely-informational notices vanish on their own. Anything the
//: user might need to act on — a failure, or a finished export with its
//: buttons — stays until dismissed.
const AUTO_DISMISS_MS = { info: 5000, success: 0, progress: 0, warn: 0, error: 0 };

let seq = 0;
const live = new Map();

function container() {
  let node = $("#toasts");
  if (!node) {
    node = el("div", { id: "toasts", role: "status", "aria-live": "polite" });
    document.body.append(node);
  }
  return node;
}

function render(entry) {
  const { id, kind, text, detail, actions, percent } = entry;
  const node = el(
    "div",
    { class: `toast toast-${kind}`, dataset: { id } },
    el(
      "div",
      { class: "toast-body" },
      el(
        "div",
        { class: "toast-line" },
        el("span", { class: "toast-text" }, text),
        typeof percent === "number"
          ? el("span", { class: "toast-percent" }, `${percent}%`)
          : null,
        // An action is a real link when it points somewhere. That gives
        // right-click, middle-click and "save as" for free, and means a
        // download needs no JavaScript at all.
        ...(actions || []).map((action) =>
          action.href
            ? el(
                "a",
                {
                  class: "toast-action",
                  href: action.href,
                  download: action.download || null,
                  target: action.newTab ? "_blank" : null,
                  rel: action.newTab ? "noopener" : null,
                },
                action.label
              )
            : el(
                "button",
                { type: "button", class: "toast-action", onclick: () => action.run(id) },
                action.label
              )
        )
      ),
      detail ? el("div", { class: "toast-detail" }, detail) : null,
      typeof percent === "number"
        ? el(
            "div",
            { class: "toast-bar" },
            el("span", { style: `width:${Math.max(2, percent)}%` })
          )
        : null
    ),
    el(
      "button",
      {
        type: "button",
        class: "toast-close",
        "aria-label": "Dismiss",
        title: "Dismiss",
        onclick: () => dismiss(id),
      },
      "✕"
    )
  );
  return node;
}

function paint(entry) {
  const fresh = render(entry);
  if (entry.node && entry.node.isConnected) {
    entry.node.replaceWith(fresh);
  } else {
    container().append(fresh);
  }
  entry.node = fresh;

  clearTimeout(entry.timer);
  const after = AUTO_DISMISS_MS[entry.kind] || 0;
  if (after) entry.timer = setTimeout(() => dismiss(entry.id), after);
}

/** Show a notification. Returns its id, for `update` and `dismiss`. */
export function notify(text, options = {}) {
  const kind = KINDS.has(options.kind) ? options.kind : "info";
  const id = options.id || `t${++seq}`;
  const entry = { ...options, id, kind, text, node: live.get(id)?.node };
  live.set(id, entry);
  paint(entry);
  return id;
}

/** Change an existing notification in place; no-op if it is already gone. */
export function update(id, patch) {
  const entry = live.get(id);
  if (!entry) return;
  Object.assign(entry, patch);
  if (patch.kind && !KINDS.has(patch.kind)) entry.kind = "info";
  paint(entry);
}

export function dismiss(id) {
  const entry = live.get(id);
  if (!entry) return;
  clearTimeout(entry.timer);
  if (entry.node && entry.node.isConnected) entry.node.remove();
  live.delete(id);
}

export function dismissAll() {
  for (const id of [...live.keys()]) dismiss(id);
}

/** Report a failure. Errors stay put until dismissed. */
export function fail(error) {
  const message = error && error.message ? error.message : String(error);
  if (error instanceof Error) console.error(error);
  return notify(message, { kind: "error" });
}

/** A quiet status line. Passing an empty string clears nothing — use dismiss. */
export function say(text, kind = "info") {
  if (!text) return null;
  return notify(text, { kind });
}
