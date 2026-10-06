import type { HistoryItem, NoorResponse, NoorState } from "@/types/noor";

const STORAGE_KEY = "noor-state-v1";

export const defaultState: NoorState = {
  child: { name: "سارة", age: 7, focusMode: true, sessionLength: 5, sound: true, speechRate: 0.85 },
  history: [],
  mastery: {},
  decisions: [],
};

export function loadState(): NoorState {
  if (typeof window === "undefined") return defaultState;
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved ? { ...defaultState, ...JSON.parse(saved) } : defaultState;
  } catch {
    return defaultState;
  }
}

export function saveState(state: NoorState) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  window.dispatchEvent(new Event("noor-state"));
}

export function saveResponse(response: NoorResponse) {
  const state = loadState();
  const item: HistoryItem = {
    id: `${Date.now()}`,
    date: new Date().toISOString(),
    status: response.status === "ok" ? "answered" : "referred",
    response,
    stars: 0,
    durationMinutes: 0,
  };
  state.history = [item, ...state.history].slice(0, 30);
  saveState(state);
  window.sessionStorage.setItem("noor-current", item.id);
  return item;
}

export function updateSession(id: string, topic: string | null, stars: number, decisions: string[], minutes?: number) {
  const state = loadState();
  const item = state.history.find((entry) => entry.id === id);
  if (item) {
    item.stars = stars;
    item.durationMinutes = minutes ?? state.child.sessionLength; // real time spent in the session
  }
  if (topic) state.mastery[topic] = Math.min(1, (state.mastery[topic] ?? 0) + stars * 0.08);
  state.decisions = [...decisions, ...state.decisions].slice(0, 12);
  saveState(state);
}

export function clearState() {
  window.localStorage.removeItem(STORAGE_KEY);
  window.sessionStorage.removeItem("noor-current");
}