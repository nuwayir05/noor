import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Info, Mic, UserRound } from "lucide-react";
import { useEffect, useState } from "react";

import { Chip, NoorButton, ParentShell } from "@/components/noor";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { loadState, saveState } from "@/lib/noor-store";

const suggestions = ["ليش نتوضأ؟","ليش الوضوء بهذا الترتيب؟","كم صلاة نصلي في اليوم؟","ليش نقول بسم الله قبل الأكل؟","وش أقول قبل ما أنام؟","ليش نقول السلام عليكم؟"];

export const Route = createFileRoute("/ask")({
  head: () => ({ meta: [{ title: "اسأل سؤال طفلك | نور" },{ name:"description",content:"ابدأ رحلة نور بسؤال طفلك."},{property:"og:title",content:"اسأل سؤال طفلك | نور"},{property:"og:description",content:"ابدأ رحلة تعلم قصيرة تناسب طفلك."},{property:"og:type",content:"website"},{name:"twitter:card",content:"summary_large_image"}] }),
  component: AskPage,
});

function AskPage() {
  const navigate = useNavigate(); const [question,setQuestion]=useState(""); const [name,setName]=useState("سارة"); const [age,setAge]=useState(7); const [focus,setFocus]=useState(true); const [soon,setSoon]=useState(false);
  useEffect(()=>{const state=loadState();setName(state.child.name);setAge(state.child.age);setFocus(state.child.focusMode)},[]);
  const submit=()=>{const state=loadState();state.child={...state.child,name:name.trim()||"سارة",age,focusMode:focus};saveState(state);window.sessionStorage.setItem("noor-question",question.trim());void navigate({to:"/processing"})};
  return <ParentShell><main className="mx-auto max-w-3xl px-5 py-10 md:py-14"><div><p className="text-sm font-bold text-primary">خطوة واحدة ونبدأ</p><h1 className="mt-2 text-3xl font-bold">ما سؤال طفلك اليوم؟</h1></div><section className="mt-8 rounded-[20px] border border-border p-5 shadow-soft"><div className="flex items-center gap-4"><span className="grid h-12 w-12 place-items-center rounded-full bg-secondary"><UserRound /></span><div className="flex-1"><label className="text-sm text-muted-foreground">اسم الطفل</label><input value={name} onChange={e=>setName(e.target.value)} className="block w-full border-0 bg-transparent text-lg font-bold outline-none" /></div><div><label className="text-sm text-muted-foreground">العمر</label><select value={age} onChange={e=>setAge(Number(e.target.value))} className="block rounded-xl border border-border bg-background px-3 py-2 font-bold">{[3,4,5,6,7,8,9,10,11,12].map(n=><option key={n}>{n}</option>)}</select></div></div></section><section className="mt-6"><div className="relative"><Textarea maxLength={200} value={question} onChange={e=>setQuestion(e.target.value)} placeholder="اكتب سؤال طفلك كما قاله... مثال: ليش نقول بسم الله قبل الأكل؟" className="min-h-40 rounded-[20px] border-2 bg-background p-5 pe-16 text-lg leading-8 shadow-soft focus-visible:ring-2" /><Button type="button" variant="ghost" size="icon" onClick={()=>{setSoon(true);window.setTimeout(()=>setSoon(false),1800)}} aria-label="الإدخال الصوتي" className="absolute end-4 top-4 rounded-full"><Mic /></Button></div><div className="mt-2 flex justify-between text-sm text-muted-foreground"><span>{soon ? "قريبًا" : "اكتب السؤال بطريقتكم"}</span><span>{question.length}/٢٠٠</span></div></section><section className="mt-7"><h2 className="font-bold">أسئلة يسألها الأطفال كثيرًا</h2><div className="mt-3 flex flex-wrap gap-2">{suggestions.map(q=><Chip key={q} onClick={()=>setQuestion(q)} active={question===q}>{q}</Chip>)}</div></section><section className="mt-7 flex items-start justify-between gap-5 rounded-[20px] bg-child p-5"><div><h2 className="font-bold">وضع التركيز</h2><p className="mt-1 text-sm leading-6 text-muted-foreground">جلسات أقصر، ونشاط أكثر، واستراحة حركة.</p><p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground"><Info className="size-4" /> لا نطلب أي تشخيص. هذا الإعداد يغيّر طريقة العرض فقط.</p></div><Switch dir="ltr" checked={focus} onCheckedChange={setFocus} className="mt-1 scale-125" /></section><NoorButton className="mt-8 w-full" disabled={question.trim().length<5} onClick={submit}>ابدأ الرحلة</NoorButton></main></ParentShell>;
}