import { Link } from "@tanstack/react-router";
import { Check, Headphones, LockKeyhole, Star } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { loadState } from "@/lib/noor-store";
import { ttsUrl } from "@/services/noorApi";
import { cn } from "@/lib/utils";
import type { Passage } from "@/types/noor";

export function Brand({ compact = false }: { compact?: boolean }) {
  return <img src="/noor-logo.svg" alt="نور" className={cn("object-contain", compact ? "h-14 w-auto" : "h-20 w-auto md:h-24")} />;
}

export function ParentShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      <FloatingStars subtle />
      <header className="relative border-b border-border/70 bg-background/95">
        <div className="mx-auto flex h-20 max-w-6xl items-center justify-between px-5 md:px-8">
          <Link to="/" aria-label="الصفحة الرئيسية"><Brand compact /></Link>
          <nav className="flex items-center gap-1 text-sm font-semibold text-primary md:gap-3">
            <Link to="/ask" className="rounded-full px-3 py-2 hover:bg-secondary">اسأل</Link>
            <Link to="/parent" className="rounded-full px-3 py-2 hover:bg-secondary">لوحة ولي الأمر</Link>
          </nav>
        </div>
      </header>
      {children}
    </div>
  );
}

export function ChildShell({ step, total = 6, children, onParent }: { step: number; total?: number; children: ReactNode; onParent?: () => void }) {
  const [holding, setHolding] = useState(false);
  useEffect(() => {
    if (!holding || !onParent) return;
    const timer = window.setTimeout(onParent, 2000);
    return () => window.clearTimeout(timer);
  }, [holding, onParent]);
  return (
    <div className="relative min-h-screen bg-child px-5 py-5 md:px-8">
      <FloatingStars />
      <div className="relative mx-auto flex min-h-[calc(100vh-2.5rem)] max-w-3xl flex-col">
        <div className="flex items-center justify-between">
          <div className="flex gap-2" aria-label={`الخطوة ${step} من ${total}`}>
            {Array.from({ length: total }, (_, index) => <span key={index} className={cn("h-2.5 w-8 rounded-full transition-colors", index < step ? "bg-gold" : "bg-sky")} />)}
          </div>
          <Button variant="ghost" size="icon" aria-label="اضغط مطولًا لفتح منطقة ولي الأمر" onPointerDown={() => setHolding(true)} onPointerUp={() => setHolding(false)} onPointerLeave={() => setHolding(false)}><LockKeyhole /></Button>
        </div>
        <main className="flex flex-1 flex-col justify-center py-8">{children}</main>
      </div>
    </div>
  );
}

export function NoorButton({ child = false, className, ...props }: React.ComponentProps<typeof Button> & { child?: boolean }) {
  return <Button className={cn("rounded-2xl font-bold", child ? "min-h-16 w-full text-xl" : "min-h-12 px-6 text-base", className)} {...props} />;
}

export function Chip({ children, active, onClick }: { children: ReactNode; active?: boolean; onClick?: () => void }) {
  return <Button type="button" variant={active ? "default" : "secondary"} onClick={onClick} className="h-auto min-h-11 whitespace-normal rounded-full px-5 py-2.5 text-right text-sm font-semibold">{children}</Button>;
}

export function OwlBadge({ className }: { className?: string }) {
  return <img src="/noor-owl.svg" alt="نور، المرشد" className={cn("mx-auto h-28 w-28 object-contain", className)} />;
}

// "استمع": a natural Arabic voice from the Noor server; if that is not reachable, the browser's own Arabic voice.
let currentAudio: HTMLAudioElement | null = null;

function speechRate() {
  try { return loadState().child.speechRate || 0.85; } catch { return 0.85; }
}

function bestBrowserVoice(): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith("ar"));
  const score = (v: SpeechSynthesisVoice) =>
    (/natural|online|neural/i.test(v.name) ? 4 : 0) + (/google/i.test(v.name) ? 3 : 0) + (v.lang.toLowerCase() === "ar-sa" ? 2 : 0);
  return voices.sort((a, b) => score(b) - score(a))[0];
}

function browserSpeak(text: string) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text.replace(/ﷺ/g, " صلى الله عليه وسلم "));
  const voice = bestBrowserVoice();
  if (voice) u.voice = voice;
  u.lang = voice?.lang ?? "ar-SA";
  u.rate = speechRate();
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

export function stopSpeaking() {
  currentAudio?.pause();
  currentAudio = null;
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}

export function ListenButton({ text }: { text: string }) {
  const [busy, setBusy] = useState(false);
  useEffect(() => () => stopSpeaking(), []);
  if (!text) return null;
  const listen = async () => {
    stopSpeaking();
    setBusy(true);
    try {
      const audio = new Audio(ttsUrl(text));
      audio.playbackRate = Math.min(1.4, Math.max(0.7, speechRate() / 0.85));
      currentAudio = audio;
      // play() is called straight from the tap (phones block sound that starts later)
      const playing = audio.play();
      let timer = 0;
      await Promise.race([
        playing,
        new Promise<void>((_, reject) => { audio.onerror = () => reject(new Error("tts")); }),
        new Promise<void>((_, reject) => { timer = window.setTimeout(() => reject(new Error("slow")), 8000); }),
      ]).finally(() => window.clearTimeout(timer));
    } catch {
      currentAudio?.pause();
      currentAudio = null;
      browserSpeak(text);
    } finally {
      setBusy(false);
    }
  };
  return <Button type="button" variant="secondary" onClick={() => void listen()} disabled={busy} className="min-h-12 rounded-full px-5 text-base"><Headphones /> {busy ? "لحظة…" : "استمع"}</Button>;
}

const FLOATING_STARS = [
  { top: "12%", insetInlineStart: "8%", size: 18, delay: "0s", gold: true },
  { top: "22%", insetInlineStart: "82%", size: 14, delay: "1.4s", gold: false },
  { top: "48%", insetInlineStart: "16%", size: 12, delay: "2.8s", gold: false },
  { top: "60%", insetInlineStart: "88%", size: 20, delay: "0.9s", gold: true },
  { top: "78%", insetInlineStart: "30%", size: 14, delay: "2.1s", gold: true },
  { top: "85%", insetInlineStart: "70%", size: 12, delay: "3.5s", gold: false },
  { top: "35%", insetInlineStart: "55%", size: 10, delay: "4.2s", gold: false },
];

const SUBTLE_STARS = [
  { top: "14%", insetInlineStart: "90%", size: 14, delay: "0s", gold: true },
  { top: "38%", insetInlineStart: "6%", size: 12, delay: "1.8s", gold: false },
  { top: "64%", insetInlineStart: "92%", size: 10, delay: "3.2s", gold: false },
  { top: "84%", insetInlineStart: "12%", size: 12, delay: "2.4s", gold: true },
];

export function FloatingStars({ subtle = false }: { subtle?: boolean }) {
  const stars = subtle ? SUBTLE_STARS : FLOATING_STARS;
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {stars.map((star, index) => (
        <Star
          key={index}
          className={cn("star-float absolute", star.gold ? "fill-gold/40 text-gold/40" : "fill-primary/20 text-primary/20", subtle && "opacity-60")}
          style={{ top: star.top, insetInlineStart: star.insetInlineStart, width: star.size, height: star.size, animationDelay: star.delay }}
        />
      ))}
    </div>
  );
}

export function StarReward({ count = 1 }: { count?: number }) {
  return <div className="inline-flex items-center gap-2 rounded-full bg-cream px-4 py-2 font-bold text-primary"><Star className="fill-gold text-gold" /> {count}</div>;
}

export function SourceCard({ passage }: { passage: Passage }) {
  return (
    <article className="rounded-[20px] border border-border bg-card p-5 shadow-soft">
      <div className="mb-4 flex items-center justify-between gap-3"><span className="rounded-full bg-secondary px-3 py-1 text-xs font-bold text-primary">{passage.type === "quran" ? "قرآن كريم" : "حديث"}</span><span className="inline-flex items-center gap-1 text-sm text-muted-foreground"><Check className="size-4 text-primary" /> راجعهُ: {passage.reviewer}</span></div>
      <p className={cn("text-lg leading-9 text-foreground", passage.type === "quran" && "font-quran")}>{passage.text}</p>
      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted-foreground"><span>{passage.source}</span>{passage.grade && <span>الدرجة: {passage.grade}</span>}{passage.partial_ayah && <span>من الآية</span>}</div>
      {passage.link && <a className="mt-4 inline-block font-bold text-primary underline underline-offset-4" href={passage.link} target="_blank" rel="noreferrer">المصدر الأصلي</a>}
    </article>
  );
}


// Each pre-made story has its own 4 pictures: public/images/story_<slug>_<1-4>.png
export const STORY_SLUG: Record<string, string> = {
  "الطهارة والوضوء": "wudu",
  "آداب الطعام": "eating",
  "أذكار النوم والاستيقاظ": "sleep",
  "السلام والأخلاق": "salam",
};

// Story pictures at public/images/<key>.png. Tries each key in order; if none exists, a soft placeholder
// (never a broken image).
export function Illustration({ imageKey, fallbackKey, className }: { imageKey?: string | null; fallbackKey?: string | null; className?: string }) {
  const keys = [imageKey, fallbackKey].filter((k): k is string => !!k);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => setAttempt(0), [imageKey, fallbackKey]);
  const key = keys[attempt];
  if (!key) return <div className={cn("mx-auto aspect-[4/5] h-[42vh] max-h-96 rounded-[2rem] bg-sky", className)} aria-hidden />;
  return <img key={key} src={`/images/${key}.png`} alt="" onError={() => setAttempt((a) => a + 1)} className={cn("mx-auto h-[42vh] max-h-96 w-auto max-w-full rounded-[2rem] object-contain shadow-soft", className)} />;
}
