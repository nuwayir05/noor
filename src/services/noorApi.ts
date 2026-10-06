import fallbackPacks from "@/data/fallback-packs.json";
import type { LearningPack, NoorResponse } from "@/types/noor";

// What the backend actually sends: pack is null unless status = "ok".
type RawResponse = Omit<NoorResponse, "pack"> & { pack: Partial<LearningPack> | null };

// Backend address (spec section 9: VITE_NOOR_API_URL).
// - website running on the laptop (npm run dev, port 8080) -> the AI server on the same laptop, port 8000
// - website served by the AI server itself (the public Hugging Face link) -> same address ("")
function apiUrl(): string {
  const env = import.meta.env["VITE_NOOR_API_URL"] as string | undefined;
  if (env) return env.replace(/\/$/, "");
  if (typeof window === "undefined") return "";
  const { hostname, port } = window.location;
  const local = hostname === "localhost" || hostname === "127.0.0.1";
  const devServer = port === "8080" || port === "5173"; // npm run dev
  return local && devServer ? "http://localhost:8000" : "";
}
const API_URL = apiUrl();

// Natural Arabic voice from the Noor server (used by the "استمع" button).
export function ttsUrl(text: string): string {
  return `${API_URL}/tts?text=${encodeURIComponent(text.slice(0, 500))}`;
}

const OFFLINE_REASON = "نور غير متصل الآن، جرّب أحد الأسئلة المقترحة";

// Same "same question" rule as the backend (pipeline.qkey): no diacritics, unified letters, no punctuation.
export function questionKey(s: string): string {
  return String(s ?? "")
    .replace(/[​-‏⁦-⁩﻿]/g, "")
    .replace(/[ؗ-ًؚ-ْٰۖ-ۭـ]/g, "")
    .replace(/[أإآٱ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/ة/g, "ه")
    .replace(/ؤ/g, "و")
    .replace(/ئ/g, "ي")
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const EMPTY_PACK: LearningPack = {
  lesson: [],
  order_game: null,
  quiz_l1: [],
  quiz_l2: [],
  try_it: "",
  takeaway: "",
  source: "",
  story: null,
};

// The backend sends pack = null when status is not "ok". Screens always get a full pack object,
// and missing arrays become [] so "the engine skips what's missing" (spec section 9).
function normalize(r: RawResponse): NoorResponse {
  const p = r.pack ?? EMPTY_PACK;
  return {
    ...r,
    pack: {
      ...EMPTY_PACK,
      ...p,
      lesson: p.lesson ?? [],
      quiz_l1: p.quiz_l1 ?? [],
      quiz_l2: p.quiz_l2 ?? [],
      order_game: p.order_game?.steps?.length ? p.order_game : null,
      story: p.story?.frames?.length ? p.story : null,
    },
    passages: r.passages ?? [],
  };
}

function isResponse(value: unknown): value is RawResponse {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<RawResponse>;
  return ["ok", "out_of_scope", "no_match"].includes(item.status ?? "") && typeof item.question === "string";
}

// fallback-packs.json is exported by the AI team as a LIST of responses (one per suggestion chip).
// An object keyed by question also works.
const FALLBACK: Map<string, RawResponse> = (() => {
  const raw = fallbackPacks as unknown;
  const list: unknown[] = Array.isArray(raw) ? raw : raw && typeof raw === "object" ? Object.values(raw) : [];
  const map = new Map<string, RawResponse>();
  for (const item of list) if (isResponse(item)) map.set(questionKey(item.question), item);
  return map;
})();

function findFallback(question: string): NoorResponse | undefined {
  const hit = FALLBACK.get(questionKey(question));
  return hit ? normalize({ ...hit, question, cached: true }) : undefined;
}

function offlineReferral(question: string): NoorResponse {
  return normalize({
    status: "no_match",
    question,
    topic: null,
    cached: false,
    pack: null,
    passages: [],
    referral: { reason: OFFLINE_REASON, offline: true },
  });
}

export async function ask(question: string, age: number, offline = false): Promise<NoorResponse> {
  if (offline) return findFallback(question) ?? offlineReferral(question);
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 60_000);
  try {
    const response = await fetch(`${API_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, age }),
      signal: controller.signal,
    });
    const data: unknown = await response.json();
    if (!response.ok || !isResponse(data)) throw new Error("invalid-response");
    return normalize(data);
  } catch {
    return findFallback(question) ?? offlineReferral(question);
  } finally {
    window.clearTimeout(timer);
  }
}

export async function health() {
  try {
    const response = await fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(3000) });
    return response.ok;
  } catch {
    return false;
  }
}
