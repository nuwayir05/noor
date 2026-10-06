import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, BookOpenCheck, Clock3, ShieldCheck, Sparkles, type LucideIcon } from "lucide-react";

import { Brand, FloatingStars, NoorButton, ParentShell } from "@/components/noor";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [
    { title: "نور | رحلة تعلم قصيرة لكل سؤال" },
    { name: "description", content: "نور يحوّل أسئلة طفلك الدينية إلى رحلة تعلم قصيرة وممتعة من مصادر موثوقة." },
    { property: "og:title", content: "نور | رحلة تعلم قصيرة لكل سؤال" },
    { property: "og:description", content: "تعلم ديني هادئ وممتع للأطفال من 6 إلى 10 سنوات." },
    { property: "og:type", content: "website" }, { name: "twitter:card", content: "summary_large_image" },
  ]}),
  component: HomePage,
});

function HomePage() {
  const trustItems: Array<[LucideIcon, string]> = [[Clock3,"جلسات قصيرة ≈ ٥ دقائق"],[ShieldCheck,"بدون تشخيص أو بيانات حساسة"],[BookOpenCheck,"من مصادر موثوقة راجعها مختص"]];
  return <ParentShell>
    <main>
      <section className="relative overflow-hidden bg-child px-5 pb-14 pt-10 md:pb-20 md:pt-16">
        <FloatingStars />
        <div className="relative mx-auto grid max-w-6xl items-center gap-10 md:grid-cols-[1.1fr_.9fr]">
          <div className="max-w-2xl"><span className="mb-5 inline-flex rounded-full bg-cream px-4 py-2 text-sm font-bold text-primary">تعلم يناسب إيقاع طفلك</span><h1 className="text-4xl font-bold leading-[1.35] text-foreground md:text-6xl">رحلة تعلم قصيرة...<br /><span className="text-primary">لكل سؤال</span></h1><p className="mt-5 max-w-xl text-xl leading-9 text-muted-foreground md:text-2xl">نحوّل أسئلة طفلك الدينية إلى رحلة قصيرة وممتعة.</p><NoorButton asChild className="mt-8"><Link to="/ask">اسأل سؤال طفلك <ArrowLeft /></Link></NoorButton></div>
          <div className="relative mx-auto grid min-h-80 w-full max-w-md place-items-center rounded-[3rem] bg-sky/70"><div className="absolute start-5 top-5 h-16 w-16 rounded-full bg-cream" /><div className="relative rounded-[2.5rem] bg-background p-8 shadow-soft"><Brand /><div className="mt-4 flex justify-center gap-3 text-gold"><Sparkles className="size-7" /><Sparkles className="size-5" /></div></div></div>
        </div>
      </section>
      <section className="px-5 py-14 md:py-20"><div className="mx-auto max-w-6xl"><h2 className="text-center text-3xl font-bold">كيف تبدأ الرحلة؟</h2><div className="mt-10 grid gap-5 md:grid-cols-3">{[["١","اسأل","اكتب سؤال طفلك كما قاله"],["٢","تحقق من المصدر","نبحث في المحتوى الذي راجعه مختص"],["٣","يتعلم طفلك ويلعب","رحلة قصيرة بخطوات واضحة"]].map(([n,t,d])=><article key={n} className="rounded-[20px] border border-border bg-card p-7 shadow-soft"><span className="grid h-11 w-11 place-items-center rounded-full bg-secondary font-bold text-primary">{n}</span><h3 className="mt-5 text-xl font-bold">{t}</h3><p className="mt-2 leading-7 text-muted-foreground">{d}</p></article>)}</div></div></section>
      <section className="border-y border-border bg-secondary/45 px-5 py-8"><div className="mx-auto grid max-w-6xl gap-4 md:grid-cols-3">{trustItems.map(([Icon,text])=><div key={text} className="flex items-center gap-3 font-semibold"><Icon className="size-6 text-primary" /><span>{text}</span></div>)}</div></section>
    </main><footer className="px-5 py-8 text-center text-sm text-muted-foreground">فريق مشكاة · Track 03 · AI Challenge for Serving Islamic Content</footer>
  </ParentShell>;
}