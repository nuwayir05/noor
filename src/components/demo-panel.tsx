import { useEffect, useState } from "react";
import { FlaskConical, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { loadState } from "@/lib/noor-store";

export function DemoPanel() {
  const [open, setOpen] = useState(false);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("demo") === "1") setOpen(true);
    setOffline(window.localStorage.getItem("noor-demo-offline") === "1");
    const key = (event: KeyboardEvent) => { if (event.key.toLowerCase() === "d" && !(event.target instanceof HTMLInputElement) && !(event.target instanceof HTMLTextAreaElement)) setOpen((value) => !value); };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  if (!open) return null;
  const state = loadState();
  const go = (path: string) => { window.location.href = path; };
  return <aside dir="rtl" className="fixed bottom-4 start-4 z-50 w-[min(22rem,calc(100vw-2rem))] rounded-[20px] border border-primary/30 bg-background p-4 shadow-2xl">
    <div className="flex items-center justify-between"><h2 className="flex items-center gap-2 font-bold"><FlaskConical className="text-primary" /> لوحة العرض</h2><Button variant="ghost" size="icon" onClick={() => setOpen(false)} aria-label="إغلاق"><X /></Button></div>
    <div className="mt-4 grid grid-cols-2 gap-2"><Button variant="secondary" onClick={() => go("/")}>الرئيسية</Button><Button variant="secondary" onClick={() => go("/ask")}>السؤال</Button><Button variant="secondary" onClick={() => go("/processing")}>المعالجة</Button><Button variant="secondary" onClick={() => go("/referral")}>الإحالة</Button><Button variant="secondary" onClick={() => go("/parent")}>التقدم</Button><Button variant="secondary" onClick={() => go("/parent/settings")}>الإعدادات</Button></div>
    <Button className="mt-3 w-full" variant={offline ? "default" : "outline"} onClick={() => { const next=!offline; setOffline(next); window.localStorage.setItem("noor-demo-offline",next?"1":"0"); }}>{offline ? "الخادم غير متصل" : "محاكاة انقطاع الخادم"}</Button>
    <div className="mt-4 rounded-xl bg-child p-3 text-xs leading-6 text-muted-foreground"><p>المستوى الحالي: {state.history.some(h=>h.stars>=2)?"٢":"١"}</p><p>آخر قرار: {state.decisions[0]??"لم تبدأ جلسة بعد"}</p><p>الإجابات المحفوظة: {state.history.filter(h=>h.response.cached).length}</p></div>
  </aside>;
}