// The app's shared, mutable state. One owner per value.
//
// `selection` is an ORDERED list, not a Set: an export batch is a selection in
// the order you made it, and the server preserves that order too
// (store.list_cards(ids=...)). A Set would silently sort by insertion of the
// underlying hash and the printed deck order would stop matching the screen.

export const state = {
  meta: null,
  cards: [],
  tags: [],
  backs: [],
  filter: { tag: "", q: "" },
  selection: [],
  editingId: null,
  uploadTag: "",
};

const listeners = new Set();

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function emit() {
  for (const fn of listeners) fn(state);
}

export function isSelected(id) {
  return state.selection.includes(id);
}

export function toggle(id) {
  const at = state.selection.indexOf(id);
  if (at === -1) state.selection.push(id);
  else state.selection.splice(at, 1);
  emit();
}

/** Select every card between the last selected one and `id`, in grid order. */
export function selectRange(id) {
  const ids = state.cards.map((card) => card.id);
  const last = state.selection[state.selection.length - 1];
  if (last === undefined) return toggle(id);
  const from = ids.indexOf(last);
  const to = ids.indexOf(id);
  if (from === -1 || to === -1) return toggle(id);
  const [lo, hi] = from < to ? [from, to] : [to, from];
  for (const candidate of ids.slice(lo, hi + 1)) {
    if (!state.selection.includes(candidate)) state.selection.push(candidate);
  }
  emit();
}

export function selectAll() {
  state.selection = state.cards.map((card) => card.id);
  emit();
}

export function clearSelection() {
  state.selection = [];
  emit();
}

export function selectedCards() {
  const byId = new Map(state.cards.map((card) => [card.id, card]));
  return state.selection.map((id) => byId.get(id)).filter(Boolean);
}
