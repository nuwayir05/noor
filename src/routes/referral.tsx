import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Star } from "lucide-react";
import { useEffect, useState } from "react";
import { Chip, NoorButton, OwlBadge, ParentShell } from "@/components/noor";
import { loadState } from "@/lib/noor-store";
import type { HistoryItem } from "@/types/noor";

export const Route=createFileRoute("/referral")({head:()=>({meta:[{title:"سؤال للنقاش | نور"},{name:"description",content:"مساحة آمنة للأسئلة التي تحتاج حديثًا مع ولي الأمر."},{property:"og:title",content:"سؤال للنقاش | نور"},{property:"og:description",content:"مساحة آمنة للأسئلة التي تحتاج حديثًا مع ولي الأمر."},{property:"og:type",content:"website"},{name:"twitter:card",content:"summary_large_image"}]}),component:ReferralPage});

// Fixed wording from the spec (P4). The backend's internal reason is not shown to families.
const NOTE_OUT_OF_SCOPE = "هذا السؤال خارج المواضيع التي راجعها مختصونا حاليًا، لذلك لم نُجب عنه. أضفناه إلى قائمة (أسئلة للنقاش) في لوحتك.";
const NOTE_NO_MATCH = "لم نجد في نصوصنا المعتمدة ما يجيب عن هذا السؤال بدقة، لذلك لم نُجب عنه. أضفناه إلى قائمة (أسئلة للنقاش) في لوحتك.";
const NOTE_OFFLINE = "نور غير متصل الآن، جرّب أحد الأسئلة المقترحة";
const CHIPS = ["ليش نتوضأ؟", "ليش نقول بسم الله قبل الأكل؟", "كم صلاة نصلي في اليوم؟"];

function ReferralPage() {
  const navigate = useNavigate();
  const [item, setItem] = useState<HistoryItem>();
  useEffect(() => { const id = window.sessionStorage.getItem("noor-current"); setItem(loadState().history.find((x) => x.id === id)); }, []);
  const r = item?.response;
  const note = r?.referral?.offline ? NOTE_OFFLINE : r?.status === "out_of_scope" ? NOTE_OUT_OF_SCOPE : NOTE_NO_MATCH;
  const askAgain = (q: string) => { window.sessionStorage.setItem("noor-question", q); void navigate({ to: "/processing" }); };
  return (
    <ParentShell>
      <main className="mx-auto max-w-2xl px-5 py-12 text-center">
        <OwlBadge />
        <div className="mx-auto mt-6 max-w-xl rounded-[20px] bg-cream p-7">
          <Star className="mx-auto size-8 fill-gold text-gold" />
          <h1 className="mt-4 text-2xl font-bold leading-10">سؤال رائع! هذا السؤال مهم، والأفضل أن تجيبك عنه ماما أو بابا أو معلمك.</h1>
        </div>
        <div className="mt-6 rounded-[20px] border border-border p-6 text-right shadow-soft">
          {r?.question && <p className="font-bold">{r.question}</p>}
          <p className="mt-2 leading-8 text-muted-foreground">{note}</p>
        </div>
        <NoorButton asChild className="mt-8"><Link to="/ask">اسأل سؤالًا آخر</Link></NoorButton>
        <div className="mt-6 flex flex-wrap justify-center gap-2">{CHIPS.map((q) => <Chip key={q} onClick={() => askAgain(q)}>{q}</Chip>)}</div>
      </main>
    </ParentShell>
  );
}
