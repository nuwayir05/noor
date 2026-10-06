// Rule-based adaptive engine (spec section 8). No AI call. Every decision returns a short Arabic reason
// for the parent's "how the journey adapted" feed.
export type AdaptiveSignal = "correct" | "mistake" | "skip" | "rushed" | "slow" | "idle" | "break_done";
export type EngineState = {
  level: 1 | 2;
  correctStreak: number;
  mistakes: number;
  skips: number;
  slow: number;
  correctTotal: number;
  answered: number;
  hadBreak: boolean;
  fewerLessons: boolean;
};

export const initialEngine: EngineState = {
  level: 1,
  correctStreak: 0,
  mistakes: 0,
  skips: 0,
  slow: 0,
  correctTotal: 0,
  answered: 0,
  hadBreak: false,
  fewerLessons: false,
};

export const STEADY = "";

export function adapt(state: EngineState, signal: AdaptiveSignal, name = "طفلك") {
  const next = { ...state };
  let decision = STEADY;
  let needBreak = false;

  if (signal === "correct") {
    next.correctStreak += 1;
    next.correctTotal += 1;
    next.answered += 1;
    next.mistakes = 0;
    if (next.correctStreak >= 2 && next.level === 1) {
      next.level = 2;
      decision = `رفعنا المستوى بعد إجابتين صحيحتين متتاليتين من ${name}`;
    }
  }
  if (signal === "mistake") {
    next.mistakes += 1;
    next.answered += 1;
    next.correctStreak = 0;
    if (next.mistakes >= 2) {
      next.level = 1;
      next.mistakes = 0;
      decision = "خففنا المستوى وقدّمنا النشاط بطريقة أبسط";
    }
  }
  if (signal === "skip" || signal === "rushed") {
    next.skips += 1;
    if (next.skips >= 2 && !next.fewerLessons) {
      next.fewerLessons = true;
      decision = `انتقلنا إلى لعبة واختصرنا الشرح بعد تجاوز ${name} جزأين بسرعة`;
    }
  }
  if (signal === "slow") {
    next.slow += 1;
    if (next.slow >= 3) {
      next.slow = 0;
      needBreak = true;
      decision = "أضفنا استراحة حركة قصيرة بعد ثلاث إجابات بطيئة";
    }
  }
  if (signal === "idle") {
    needBreak = true;
    decision = "أضفنا استراحة حركة قصيرة لاستعادة التركيز";
  }
  if (signal === "break_done") next.hadBreak = true;

  return { state: next, decision, needBreak };
}

// "Engaged child (no break, mostly correct) and the pack has a story -> offer the story as a reward."
export function earnedStory(state: EngineState) {
  return !state.hadBreak && state.answered > 0 && state.correctTotal / state.answered >= 0.5;
}
