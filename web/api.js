// Every request to the server goes through here.
//
// Nothing in web/ types a print measurement: the numbers all arrive from
// /api/meta, which serves dixitgen.spec. tools/check_geometry_literals.py
// scans this directory and fails the build if one appears.
//
// Cards and backs are the same shape of resource — both are an image with a
// name and a crop focus — so the verbs are generic and take a `kind` of
// "cards" or "backs". That is what lets one editor serve both.

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

function uploadForm(files, extra = {}) {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  for (const [key, value] of Object.entries(extra)) {
    if (value) form.append(key, value);
  }
  return form;
}

export const api = {
  meta: () => request("/api/meta"),

  // -- generic over cards and backs ----------------------------------------
  update: (kind, id, fields) => request(`/api/${kind}/${id}`, json("PUT", fields)),
  setFocus: (kind, id, x, y) =>
    request(`/api/${kind}/${id}/focus`, json("PUT", { x, y })),
  remove: (kind, id) => request(`/api/${kind}/${id}`, { method: "DELETE" }),

  // -- cards ---------------------------------------------------------------
  listCards: ({ tag = "", q = "" } = {}) => {
    const params = new URLSearchParams();
    if (tag) params.set("tag", tag);
    if (q) params.set("q", q);
    const query = params.toString();
    return request(`/api/cards${query ? `?${query}` : ""}`);
  },
  uploadCards: (files, tag = "") =>
    request("/api/cards/upload", {
      method: "POST",
      body: uploadForm(files, { tag }),
    }),

  listTags: () => request("/api/tags"),

  // -- backs ---------------------------------------------------------------
  listBacks: () => request("/api/backs"),
  uploadBacks: (files) =>
    request("/api/backs/upload", { method: "POST", body: uploadForm(files) }),

  // -- export --------------------------------------------------------------
  // Starts a job and returns straight away; poll exportStatus for progress.
  startExport: (payload) => request("/api/export", json("POST", payload)),
  exportStatus: (jobId) => request(`/api/export/status/${jobId}`),
};
