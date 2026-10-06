import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Check, Info } from "lucide-react";
import { useEffect, useState } from "react";

import { FloatingStars, OwlBadge } from "@/components/noor";
import { loadState, saveResponse } from "@/lib/noor-store";
import { ask } from "@/services/noorApi";

const steps = ["فهمنا السؤال", "تأكدنا أنه ضمن مواضيعنا", "وجدنا الإجابة في المصادر", "جهّزنا رحلتك"];
const STEP_MS = 600; // spec: each step stays visible at least 0.6 s, even for an instant (cached) answer

export const Route=createFileRoute("/processing")({head:()=>({meta:[{title:"نجهّز رحلتك | نور"},{name:"description",content:"نور يجهّز رحلة تعلم طفلك بهدوء."},{property:"og:title",content:"نجهّز رحلتك | نور"},{property:"og:description",content:"نور يجهّز رحلة تعلم طفلك بهدوء."},{property:"og:type",content:"website"},{name:"twitter:card",content:"summary_large_image"}]}),component:ProcessingPage});

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

function ProcessingPage() {
  const navigate = useNavigate();
  const [active, setActive] = useState(0);
  const [stopAt, setStopAt] = useState<{ index: number; label: string } | null>(null);
  const [long, setLong] = useState(false);

  useEffect(() => {
    let alive = true;
    const t1 = window.setTimeout(() => alive && setActive((a) => Math.max(a, 1)), STEP_MS);
    const t2 = window.setTimeout(() => alive && setActive((a) => Math.max(a, 2)), STEP_MS * 2);
    const wait = window.setTimeout(() => alive && setLong(true), 25_000);
    const run = async () => {
      const question = window.sessionStorage.getItem("noor-question") ?? "";
      if (!question) { void navigate({ to: "/ask" }); return; }
      const state = loadState();
      const offline = window.localStorage.getItem("noor-demo-offline") === "1";
      const started = Date.now();
      const result = await ask(question, state.child.age, offline);
      if (!alive) return;
      // make sure steps 1–2 were each seen for 0.6 s
      const left = STEP_MS * 2 - (Date.now() - started);
      if (left > 0) await sleep(left);
      if (!alive) return;
      const item = saveResponse(result);
      if (result.status === "ok") {
        setActive(3); await sleep(STEP_MS);
        setActive(4); await sleep(STEP_MS);
        if (alive) void navigate({ to: "/session/$id", params: { id: item.id } });
      } else {
        const offlineRef = !!result.referral?.offline;
        if (result.status === "out_of_scope") { setActive(1); setStopAt({ index: 1, label: "خارج مواضيعنا" }); }
        else { setActive(2); setStopAt({ index: 2, label: offlineRef ? "نور غير متصل الآن" : "لم نجد نصًا معتمدًا" }); }
        await sleep(1400);
        if (alive) void navigate({ to: "/referral" });
      }
    };
    void run();
    return () => { alive = false; clearTimeout(t1); clearTimeout(t2); clearTimeout(wait); };
  }, [navigate]);

  return (
    <div className="relative min-h-screen overflow-hidden bg-child px-5 py-12">
      <FloatingStars />
      <main className="relative mx-auto max-w-xl text-center">
        <OwlBadge className="soft-enter" />
        <h1 className="mt-7 text-3xl font-bold">نور يجهّز رحلتك</h1>
        <p className="mt-2 text-lg text-muted-foreground">لحظات ونبدأ معًا</p>
        <div className="mt-10 space-y-3 text-right">
          {steps.map((step, i) => {
            const stopped = stopAt?.index === i;
            const done = i < active && !stopped;
            const dim = stopAt && i > stopAt.index;
            return (
              <div key={step} className={`flex items-center gap-4 rounded-2xl bg-background p-4 shadow-soft transition-opacity ${dim ? "opacity-40" : ""}`}>
                <span className={`grid h-8 w-8 place-items-center rounded-full ${stopped ? "bg-cream text-primary" : done ? "bg-primary text-primary-foreground" : "bg-secondary text-primary"}`}>
                  {stopped ? <Info className="size-5" /> : done ? <Check className="size-5" /> : i + 1}
                </span>
                <span className={`font-semibold ${done || stopped ? "text-foreground" : "text-muted-foreground"}`}>{stopped ? stopAt.label : step}</span>
              </div>
            );
          })}
        </div>
        {long && !stopAt && <p className="mt-6 text-sm text-muted-foreground">نجهّز رحلة جديدة لم نُعدّها من قبل… لحظات</p>}
      </main>
    </div>
  );
}
