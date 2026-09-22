// Every request to the server goes through here.
//
// Nothing in web/ types a print measurement: the numbers all arrive from
// /api/meta, which serves dixitgen.spec. tools/check_geometry_literals.py
// scans this directory and fails the build if one appears.

async function request(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && body.error) message = body.error;
    } catch (_) {
      /* a non-JSON error body: keep the status line */
    }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  meta: () => request("/api/meta"),

  listCards: ({ tag = "", q = "" } = {}) => {
    const params = new URLSearchParams();
    if (tag) params.set("tag", tag);
    if (q) params.set("q", q);
    const query = params.toString();
    return request(`/api/cards${query ? `?${query}` : ""}`);
  },

  uploadCards: (files, tag = "") => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    if (tag) form.append("tag", tag);
    return request("/api/cards/upload", { method: "POST", body: form });
  },

  updateCard: (id, fields) => request(`/api/cards/${id}`, json("PUT", fields)),
  setFocus: (id, x, y) => request(`/api/cards/${id}/focus`, json("PUT", { x, y })),
  deleteCard: (id) => request(`/api/cards/${id}`, { method: "DELETE" }),

  listTags: () => request("/api/tags"),

  listBacks: () => request("/api/backs"),
  uploadBacks: (files) => {
    const form = new FormData();
    for (const file of files) form.append("files", file, file.name);
    return request("/api/backs/upload", { method: "POST", body: form });
  },
  deleteBack: (id) => request(`/api/backs/${id}`, { method: "DELETE" }),

  exportBatch: (payload) => request("/api/export", json("POST", payload)),
};
