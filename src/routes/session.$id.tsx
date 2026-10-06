import { DndContext, PointerSensor, TouchSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, verticalListSortingStrategy, useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Check, GripVertical, Star } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ChildShell, Illustration, ListenButton, NoorButton, OwlBadge, StarReward, STORY_SLUG } from "@/components/noor";
import { adapt, earnedStory, initialEngine, STEADY, type AdaptiveSignal, type EngineState } from "@/engine/adaptive";
import { loadState, updateSession } from "@/lib/noor-store";
import { questionKey } from "@/services/noorApi";
import type { HistoryItem, QuizItem, Story } from "@/types/noor";

export const Route=createFileRoute("/session/$id")({head:()=>({meta:[{title:"رحلة التعلم | نور"},{name:"description",content:"جلسة تعلم قصيرة وتفاعلية للأطفال."},{property:"og:title",content:"رحلة التعلم | نور"},{property:"og:description",content:"جلسة تعلم قصيرة وتفاعلية للأطفال."},{property:"og:type",content:"website"},{name:"twitter:card",content:"summary_large_image"}]}),component:SessionPage});

type Stage = "lesson" | "order" | "quiz" | "wrap" | "try" | "story" | "break" | "reward";
type Activity = { kind: "order" } | { kind: "quiz"; item: QuizItem; level: 1 | 2 };
const IDLE_MS = 15_000;   // spec 8: idle over 15 s -> movement break
const SLOW_MS = 10_000;   // spec 8: 3 answers slower than 10 s -> movement break
const RUSHED_MS = 2_000;  // spec 8: "next" pressed in under 2 s = rushed
const MAX_BREAKS = 2;
// spec 8 (focus mode): at most 3 lesson sentences in a row, then an active item (game or question).
const CHUNK_FOCUS = 3;
const CHUNK_NORMAL = 5;
const SLOW_TOTAL_WRAP = 5; // answers this slow in one session: wind down gently instead of continuing

// Same rule as the AI's check (ai/pipeline.py: taught): at least half of the answer's content words
// must appear in what the child was taught.
const HONORIFICS = /ﷺ|ﷻ|صلى الله عليه وسلم|رضي الله عنهما|رضي الله عنهم|رضي الله عنها|رضي الله عنه|عليه السلام|عز وجل|سبحانه وتعالى|تعالى/g;
const STOPWORDS = new Set("من الي علي في عن ان انه انها لا لم لن ما ثم او ام هذا هذه ذلك تلك الذي التي الذين كان كانت قال قالت يكون هو هي هم كل بعض قد لقد اذا اذ حتي مع عند لكن بل غير بين لولا وهو وهي وان فان كما مثل اي ايضا الله النبي رسول الرسول نبي".split(" "));
const clean = (s: string) => questionKey(s.replace(/[\u0617-\u061a\u064b-\u0652\u0670\u0640]/g, "").replace(HONORIFICS, " "));
function wasTaught(answer: string, taught: string) {
  const a = clean(answer);
  const t = clean(taught);
  if (!a) return false;
  const words = a.split(" ").filter((w) => w.length >= 3 && !STOPWORDS.has(w));
  if (!words.length) return t.includes(a);
  return words.filter((w) => t.includes(w)).length / words.length >= 0.5;
}

function SessionPage() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const [item, setItem] = useState<HistoryItem>();
  const [stage, setStage] = useState<Stage>("lesson");
  const [resumeTo, setResumeTo] = useState<Stage>("lesson");
  const [lessonIndex, setLessonIndex] = useState(0);
  const [since, setSince] = useState(1);              // lesson sentences shown since the last activity
  const [inRow, setInRow] = useState(0);              // activities in a row (never the same format 3 times)
  const [slowTotal, setSlowTotal] = useState(0);      // slow answers this session
  const [wrapped, setWrapped] = useState(false);      // gentle ending already started
  const [finalQuiz, setFinalQuiz] = useState(false);  // the last, easy question is on screen
  const [sessionMinutes, setSessionMinutes] = useState(5);
  const [orderDone, setOrderDone] = useState(false);
  const [asked, setAsked] = useState<string[]>([]);   // quiz questions already asked
  const [quiz, setQuiz] = useState<{ item: QuizItem; level: 1 | 2 } | null>(null);
  const [stars, setStars] = useState(0);
  const [engine, setEngine] = useState(initialEngine);
  const [decisions, setDecisions] = useState<string[]>([]);
  const [breaks, setBreaks] = useState(0);
  const [pendingBreak, setPendingBreak] = useState(false);
  const [childName, setChildName] = useState("");
  const [focusMode, setFocusMode] = useState(true);
  const startedAt = useRef(Date.now());
  const stageStart = useRef(Date.now());
  const lastActivity = useRef(Date.now());

  useEffect(() => {
    const state = loadState();
    setItem(state.history.find((x) => x.id === id));
    setChildName(state.child.name);
    setFocusMode(state.child.focusMode);
    setSessionMinutes(state.child.sessionLength || 5);
  }, [id]);

  // Every new screen restarts the "time on screen" clock.
  useEffect(() => { stageStart.current = Date.now(); lastActivity.current = Date.now(); }, [stage, lessonIndex, quiz]);

  // Real idle detection: a break only when the child has not touched the screen for 15 s.
  useEffect(() => {
    const touch = () => { lastActivity.current = Date.now(); };
    const events = ["pointerdown", "keydown", "touchstart"] as const;
    events.forEach((e) => window.addEventListener(e, touch, { passive: true }));
    return () => events.forEach((e) => window.removeEventListener(e, touch));
  }, []);

  const goBreak = useCallback((from: Stage) => {
    setResumeTo(from === "story" ? "reward" : from);
    setBreaks((b) => b + 1);
    setStage("break");
  }, []);

  const record = useCallback((signal: AdaptiveSignal) => {
    const result = adapt(engine, signal, childName || "طفلك");
    setEngine(result.state);
    if (result.decision !== STEADY) setDecisions((d) => [result.decision, ...d]);
    return result;
  }, [engine, childName]);

  useEffect(() => {
    if (!item || stage === "break" || stage === "reward" || breaks >= MAX_BREAKS) return;
    const timer = window.setInterval(() => {
      if (Date.now() - lastActivity.current > IDLE_MS) { record("idle"); goBreak(stage); }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [item, stage, breaks, record, goBreak]);

  // a break earned by 3 slow answers starts right after the next screen is chosen
  useEffect(() => {
    if (!pendingBreak) return;
    setPendingBreak(false);
    if (stage !== "break" && stage !== "reward" && breaks < MAX_BREAKS) goBreak(stage);
  }, [pendingBreak, stage, breaks, goBreak]);

  if (!item) return <div className="grid min-h-screen place-items-center bg-child"><NoorButton onClick={() => void navigate({ to: "/ask" })}>ابدأ من السؤال</NoorButton></div>;

  const { pack, topic } = item.response;
  const chunk = focusMode ? CHUNK_FOCUS : CHUNK_NORMAL;
  const quizCap = focusMode ? 4 : 6;
  const orderSteps = pack.order_game ? (engine.level === 2 ? pack.order_game.steps : pack.order_game.steps.slice(0, 4)) : [];
  const hasStory = !!pack.story?.frames?.length;

  // What the child has been taught so far: the lesson sentences seen + the ordering steps once played.
  const taughtText = (idx: number, orderPlayed: boolean) =>
    [...pack.lesson.slice(0, idx + 1).map((l) => l.text), ...(orderPlayed ? (pack.order_game?.steps.slice(0, 4) ?? []) : [])].join(" ");

  // The adaptive engine picks the next active item: the ordering game first, then a question about what was taught.
  // Level 1: level-1 questions. Level 2: harder questions first.
  const pickActivity = (st: EngineState, idx: number, orderPlayed: boolean, askedNow: string[]): Activity | null => {
    if (pack.order_game && !orderPlayed && orderSteps.length >= 2) {
      const lessonsSoFar = taughtText(idx, false);
      const known = orderSteps.filter((step) => wasTaught(step, lessonsSoFar)).length;
      if (known * 2 >= orderSteps.length) return { kind: "order" };
    }
    if (askedNow.length >= quizCap) return null;
    const taught = taughtText(idx, orderPlayed);
    const pool: Array<[QuizItem, 1 | 2]> = st.level === 2
      ? [...pack.quiz_l2.map((q) => [q, 2] as [QuizItem, 1 | 2]), ...pack.quiz_l1.map((q) => [q, 1] as [QuizItem, 1 | 2])]
      : pack.quiz_l1.map((q) => [q, 1] as [QuizItem, 1 | 2]);
    const hit = pool.find(([q]) => !askedNow.includes(q.question) && wasTaught(q.answer, taught));
    return hit ? { kind: "quiz", item: hit[0], level: hit[1] } : null;
  };

  const startActivity = (act: Activity, row = 1) => {
    setSince(0);
    setInRow(row);
    if (act.kind === "order") { setStage("order"); return; }
    setQuiz({ item: act.item, level: act.level });
    setStage("quiz");
  };

  const toTryOrEnd = (st: EngineState) => {
    if (pack.try_it) { setStage("try"); return; }
    setStage(hasStory && earnedStory(st) ? "story" : "reward");
  };

  // One rule for "what comes next": up to `chunk` sentences in a row, then an activity; at the end, try-it.
  // Gentle ending (spec 8: session length reached -> end on a success). Never cuts a screen off:
  // it is checked only between items.
  const wrapReason = (slowNow: number) => {
    if (wrapped) return null;
    if (Date.now() - startedAt.current >= sessionMinutes * 60_000) return "time";
    if (slowNow >= SLOW_TOTAL_WRAP || breaks >= MAX_BREAKS) return "slow";
    return null;
  };

  const advance = (st: EngineState, idx: number, sinceNow: number, orderPlayed: boolean, askedNow: string[], slowNow = slowTotal) => {
    if (finalQuiz) { setFinalQuiz(false); toTryOrEnd(st); return; }
    const why = wrapReason(slowNow);
    if (why) {
      setWrapped(true);
      setDecisions((d) => [why === "time"
        ? "أنهينا الجلسة بهدوء لأن وقتها المحدد انتهى، وختمنا بنشاط سهل"
        : "أنهينا الجلسة بهدوء لأن الإجابات أخذت وقتًا طويلًا، وختمنا بنشاط سهل", ...d]);
      setStage("wrap");
      return;
    }
    const moreLessons = !st.fewerLessons && idx < pack.lesson.length - 1;
    if (moreLessons && sinceNow < chunk) { setLessonIndex(idx + 1); setSince(sinceNow + 1); setInRow(0); setStage("lesson"); return; }
    const row = sinceNow === 0 ? inRow + 1 : 1;       // sinceNow 0 = we just finished an activity
    const act = row <= 2 ? pickActivity(st, idx, orderPlayed, askedNow) : null;
    if (act) { startActivity(act, row); return; }
    if (moreLessons) { setLessonIndex(idx + 1); setSince(1); setInRow(0); setStage("lesson"); return; }
    toTryOrEnd(st);
  };

  const nextLesson = (skipped = false) => {
    const fast = Date.now() - stageStart.current < RUSHED_MS;
    const r = skipped ? record("skip") : fast ? record("rushed") : null;
    const st = r?.state ?? engine;
    // rushing or skipping twice switches to a game/question straight away (engine: fewerLessons)
    advance(st, lessonIndex, st.fewerLessons ? chunk : since, orderDone, asked);
  };

  // After an answer: level up/down, slow answers count toward a break, then the next item.
  const answered = (correct: boolean, orderPlayed: boolean, askedNow: string[]) => {
    const slow = Date.now() - stageStart.current > SLOW_MS;
    if (correct) setStars((s) => s + 1);
    let r = record(correct ? "correct" : "mistake");
    const slowNow = slowTotal + (slow ? 1 : 0);
    if (slow) setSlowTotal(slowNow);
    if (slow) {
      const s = adapt(r.state, "slow", childName || "طفلك");
      setEngine(s.state);
      if (s.decision !== STEADY) setDecisions((d) => [s.decision, ...d]);
      if (s.needBreak) setPendingBreak(true);
      r = s;
    }
    advance(r.state, lessonIndex, 0, orderPlayed, askedNow, slowNow);
  };

  const afterWrap = () => {
    // the last item is one the child is likely to get right: a level-1 question about what was taught
    const taught = taughtText(lessonIndex, orderDone);
    const easy = pack.quiz_l1.find((q) => !asked.includes(q.question) && wasTaught(q.answer, taught))
      ?? pack.quiz_l1.find((q) => asked.includes(q.question));
    if (easy) { setFinalQuiz(true); setQuiz({ item: easy, level: 1 }); setStage("quiz"); return; }
    toTryOrEnd(engine);
  };

  const afterBreak = () => {
    const r = record("break_done");
    if (wrapReason(slowTotal)) { advance(r.state, lessonIndex, 0, orderDone, asked); return; }   // time is up: gentle ending
    if (resumeTo !== "lesson") { setStage(resumeTo); return; }
    // spec 8: after a break, a shorter item (a question, not more reading)
    const act = pickActivity(r.state, lessonIndex, orderDone, asked);
    if (act) startActivity(act); else setStage("lesson");
  };

  const finish = () => {
    updateSession(id, topic, stars, decisions, Math.max(1, Math.round((Date.now() - startedAt.current) / 60000)));
    void navigate({ to: "/parent" });
  };

  // Progress dots: reading + activities fill the first four, then try-it/story, then the reward.
  const shown = stage === "break" ? resumeTo : stage;
  const step = shown === "reward" ? 6 : shown === "story" ? 5 : shown === "try" || shown === "wrap" ? (hasStory ? 4 : 5)
    : 1 + Math.min(2, Math.floor(((lessonIndex + 1) / Math.max(1, pack.lesson.length)) * 3));

  return (
    <ChildShell step={step} total={6} onParent={() => void navigate({ to: "/parent" })}>
      {stage === "lesson" && (
        <Lesson key={lessonIndex} text={pack.lesson[lessonIndex]?.text ?? ""} previous={lessonIndex ? pack.lesson[lessonIndex - 1]?.text : undefined}
          onNext={() => nextLesson(false)} onSkip={() => nextLesson(true)} />
      )}
      {stage === "order" && pack.order_game && (
        <OrderGame instruction={kidTitle(pack.order_game.instruction)} initial={orderSteps} level={engine.level}
          onDone={(firstTry) => { setOrderDone(true); answered(firstTry, true, asked); }} />
      )}
      {stage === "quiz" && quiz && (
        <Quiz key={quiz.item.question} level={quiz.level} item={quiz.item} onDone={(correct) => {
          const askedNow = [...asked, quiz.item.question];
          setAsked(askedNow);
          answered(correct, orderDone, askedNow);
        }} />
      )}
      {stage === "wrap" && <WrapUp name={childName} onDone={afterWrap} />}
      {stage === "try" && <TryIt text={pack.try_it} onDone={() => { setStars((s) => s + 1); setStage(hasStory && earnedStory(engine) ? "story" : "reward"); }} />}
      {stage === "story" && pack.story && <StoryView story={pack.story} slug={STORY_SLUG[topic ?? ""]} onStar={() => setStars((s) => s + 1)} onDone={() => setStage("reward")} />}
      {stage === "break" && <Break onDone={afterBreak} />}
      {stage === "reward" && <Reward name={childName} topic={topic ?? "موضوعًا جديدًا"} takeaway={pack.takeaway} stars={stars} onDone={finish} onParent={finish} />}
    </ChildShell>
  );
}

// "رتّب ما نفعله قبل النوم كما جاء في حديث البراء" -> "رتّب ما نفعله قبل النوم" (no narrator names the lesson never taught)
function kidTitle(instruction: string) {
  const t = (instruction || "").replace(/\s*(كما\s+(جاء|ورد)\s+)?(في|ب)\s*حديث\s+\S+.*$/u, "").replace(/\s*كما\s+(جاء|ورد)\s+في\s+\S+.*$/u, "").trim();
  return t || "رتّب الخطوات";
}

function WrapUp({ name, onDone }: { name: string; onDone: () => void }) {
  return (
    <div className="text-center soft-enter">
      <OwlBadge />
      <h1 className="mt-7 text-3xl font-bold leading-[1.5]">أحسنت{name ? ` يا ${name}` : ""}!</h1>
      <p className="mx-auto mt-4 max-w-xl text-2xl leading-[1.8]">عمل رائع اليوم. بقي نشاط أخير ثم ننتهي.</p>
      <div className="mt-5"><ListenButton text="عمل رائع اليوم. بقي نشاط أخير ثم ننتهي." /></div>
      <NoorButton child className="mt-8" onClick={onDone}>هيا</NoorButton>
    </div>
  );
}

function Lesson({ text, previous, onNext, onSkip }: { text: string; previous?: string | undefined; onNext: () => void; onSkip: () => void }) {
  return (
    <div className="text-center soft-enter">
      {previous && <span className="inline-flex max-w-full items-center gap-1 truncate rounded-full bg-secondary px-4 py-2 text-sm text-muted-foreground">قبلها: {previous} <Check className="size-4 shrink-0 text-primary" /></span>}
      <p className="mx-auto mt-8 max-w-2xl text-[26px] font-semibold leading-[1.8]">{text}</p>
      <div className="mt-5"><ListenButton text={text} /></div>
      <NoorButton child className="mt-8" onClick={onNext}>التالي</NoorButton>
      <button className="mt-3 text-sm text-muted-foreground underline" onClick={onSkip}>تجاوز</button>
    </div>
  );
}

function SortableStep({ id, text, state }: { id: string; text: string; state: "" | "right" | "wrong" }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id });
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} {...attributes} {...listeners}
      className={`flex min-h-16 touch-none items-center gap-3 rounded-2xl border-2 bg-background p-4 text-lg font-bold shadow-soft transition-colors ${state === "right" ? "border-gold bg-cream" : state === "wrong" ? "border-sky" : "border-border"}`}>
      <GripVertical className="shrink-0 text-primary" /><span>{text}</span>
    </div>
  );
}

function OrderGame({ instruction, initial, level, onDone }: { instruction: string; initial: string[]; level: 1 | 2; onDone: (firstTry: boolean) => void }) {
  const shuffled = useMemo(() => {
    const a = [...initial];
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j]!, a[i]!]; }
    if (a.every((s, i) => s === initial[i]) && a.length > 1) a.reverse();
    return a;
  }, [initial]);
  const [steps, setSteps] = useState(shuffled);
  const [note, setNote] = useState("");
  const [tries, setTries] = useState(0);
  const [checked, setChecked] = useState(false);
  const sensors = useSensors(useSensor(PointerSensor), useSensor(TouchSensor, { activationConstraint: { delay: 120, tolerance: 6 } }));
  const drag = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    setChecked(false);
    setSteps((items) => arrayMove(items, items.indexOf(String(e.active.id)), items.indexOf(String(e.over?.id))));
  };
  const check = () => {
    setChecked(true);
    if (steps.every((s, i) => s === initial[i])) { setNote("أحسنت!"); window.setTimeout(() => onDone(tries === 0), 750); }
    else { setTries((t) => t + 1); setNote("قريب! جرّب مرة ثانية"); }
  };
  return (
    <div className="soft-enter">
      <div className="text-center"><span className="rounded-full bg-cream px-4 py-2 text-sm font-bold">مستوى {level === 1 ? "١" : "٢"}</span></div>
      <h1 className="mt-5 text-center text-3xl font-bold">{instruction || "رتّب الخطوات"}</h1>
      <p className="mt-2 text-center text-lg text-muted-foreground">اسحب البطاقات حتى تصبح بالترتيب</p>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={drag}>
        <SortableContext items={steps} strategy={verticalListSortingStrategy}>
          <div className="mt-7 space-y-3">{steps.map((s, i) => <SortableStep key={s} id={s} text={s} state={!checked ? "" : s === initial[i] ? "right" : "wrong"} />)}</div>
        </SortableContext>
      </DndContext>
      {note && <p className="mt-5 text-center text-xl font-bold text-primary">{note}</p>}
      <NoorButton child className="mt-7" onClick={check}>تحقّق</NoorButton>
    </div>
  );
}

function Quiz({ level, item, onDone }: { level: 1 | 2; item?: QuizItem | undefined; onDone: (correct: boolean) => void }) {
  const [tries, setTries] = useState(0);
  const [note, setNote] = useState("");
  const [done, setDone] = useState(false);
  const options = useMemo(() => (item ? [...item.options].sort(() => 0.5 - Math.random()) : []), [item]);
  if (!item) return <NoorButton child onClick={() => onDone(true)}>التالي</NoorButton>;
  const choose = (option: string) => {
    if (done) return;
    if (option === item.answer) { setDone(true); setNote("أحسنت!"); window.setTimeout(() => onDone(tries === 0), 650); return; }
    const t = tries + 1;
    setTries(t);
    setNote("قريب! جرّب مرة ثانية");
    if (t >= 2) { setDone(true); setNote(`الجواب: ${item.answer}`); window.setTimeout(() => onDone(false), 1600); }
  };
  return (
    <div className="soft-enter">
      <div className="text-center">
        <span className="rounded-full bg-cream px-4 py-2 text-sm font-bold">مستوى {level === 1 ? "١" : "٢"}</span>
        <h1 className="mt-6 text-3xl font-bold leading-[1.5]">{item.question}</h1>
        <div className="mt-4"><ListenButton text={[item.question, ...item.options].join(". ")} /></div>
      </div>
      <div className="mt-8 grid gap-3">
        {options.map((o) => <NoorButton child key={o} variant="outline" onClick={() => choose(o)} className={done && o === item.answer ? "border-gold bg-cream" : ""}>{o}</NoorButton>)}
      </div>
      {note && <p className="mt-5 text-center text-xl font-bold text-primary">{note}</p>}
    </div>
  );
}

function TryIt({ text, onDone }: { text: string; onDone: () => void }) {
  return (
    <div className="text-center soft-enter">
      <h1 className="mt-7 text-3xl font-bold">قوم جرّبها!</h1>
      <p className="mx-auto mt-5 max-w-xl text-2xl leading-[1.8]">{text}</p>
      <div className="mt-5"><ListenButton text={text} /></div>
      <NoorButton child className="mt-8" onClick={onDone}>جرّبتها <Check /></NoorButton>
    </div>
  );
}

// C2 mini story: 4 frames on a cream panel, one at a time; the frame named in interaction.frame asks a question.
function StoryView({ story, slug, onStar, onDone }: { story: Story; slug?: string | undefined; onStar: () => void; onDone: () => void }) {
  const [index, setIndex] = useState(0);
  const [note, setNote] = useState("");
  const [solved, setSolved] = useState(false);
  const frame = story.frames[index];
  const ask = story.interaction && story.interaction.frame === index + 1 ? story.interaction : null;
  const next = () => { setNote(""); setSolved(false); if (index < story.frames.length - 1) setIndex((i) => i + 1); else onDone(); };
  const choose = (o: string) => {
    if (!ask || solved) return;
    if (o === ask.answer) { setSolved(true); setNote("أحسنت!"); onStar(); }
    else setNote("قريب! جرّب مرة ثانية");
  };
  if (!frame) return <NoorButton child onClick={onDone}>التالي</NoorButton>;
  return (
    <div className="soft-enter text-center" key={index}>
      <span className="inline-block rounded-2xl bg-background px-4 py-2 text-sm font-bold shadow-soft">قصة قصيرة · {index + 1} من {story.frames.length}</span>
      <div className="mt-5 rounded-[2rem] bg-cream p-5">
        <Illustration imageKey={slug ? `story_${slug}_${index + 1}` : frame.image} fallbackKey={frame.image} />
        <p className="mx-auto mt-5 max-w-xl text-2xl font-semibold leading-[1.8]">{frame.text}</p>
        <div className="mt-4"><ListenButton text={frame.text} /></div>
      </div>
      {ask && (
        <div className="mt-6">
          <p className="text-2xl font-bold">{ask.question}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">{ask.options.map((o) => <NoorButton child key={o} variant="outline" onClick={() => choose(o)} className={solved && o === ask.answer ? "border-gold bg-cream" : ""}>{o}</NoorButton>)}</div>
        </div>
      )}
      {note && <p className="mt-4 text-xl font-bold text-primary">{note}</p>}
      <NoorButton child className="mt-6" disabled={!!ask && !solved} onClick={next}>{index < story.frames.length - 1 ? "التالي" : "انتهت القصة"}</NoorButton>
    </div>
  );
}

function Break({ onDone }: { onDone: () => void }) {
  const [seconds, setSeconds] = useState(10);
  useEffect(() => { const t = window.setInterval(() => setSeconds((s) => Math.max(0, s - 1)), 1000); return () => clearInterval(t); }, []);
  const pct = ((10 - seconds) / 10) * 100;
  return (
    <div className="text-center soft-enter">
      <OwlBadge />
      <h1 className="mt-7 text-3xl font-bold">وقت استراحة!</h1>
      <p className="mt-4 text-2xl leading-10">قوم ومدّ يديك فوق… ٣، ٢، ١</p>
      <div className="mx-auto mt-8 grid h-28 w-28 place-items-center rounded-full text-4xl font-bold" style={{ background: `conic-gradient(var(--gold, #E8B84A) ${pct}%, var(--sky) 0)` }}>
        <span className="grid h-20 w-20 place-items-center rounded-full bg-background">{seconds}</span>
      </div>
      <NoorButton child className="mt-10" onClick={onDone}>جاهز!</NoorButton>
    </div>
  );
}

function Reward({ name, topic, takeaway, stars, onDone, onParent }: { name: string; topic: string; takeaway: string; stars: number; onDone: () => void; onParent: () => void }) {
  return (
    <div className="text-center soft-enter">
      <Star className="star-pop mx-auto size-28 fill-gold text-gold" />
      <h1 className="mt-5 text-3xl font-bold">أحسنت يا {name}!</h1>
      <p className="mt-3 text-2xl">تعلّمت اليوم: {topic}</p>
      <div className="mt-5"><StarReward count={stars} /></div>
      {takeaway && <p className="mx-auto mt-7 max-w-xl rounded-[20px] bg-cream p-5 text-xl leading-9">{takeaway}</p>}
      <div className="mt-5"><ListenButton text={takeaway} /></div>
      <NoorButton child className="mt-8" onClick={onDone}>انتهينا اليوم</NoorButton>
      <button className="mt-3 text-sm text-muted-foreground underline" onClick={onParent}>لولي الأمر</button>
    </div>
  );
}
