export type AskStatus = "ok" | "out_of_scope" | "no_match";

export type LessonItem = { text: string; evidence: string };
export type QuizItem = { question: string; options: string[]; answer: string };
export type Passage = {
  passage_id: string;
  type: "hadith" | "quran";
  text: string;
  source: string;
  grade?: string | null;
  dorar_grade?: string | null;
  partial_ayah?: boolean;
  link?: string;
  reviewer: string;
};

export type StoryFrame = { text: string; type: string; image: string };
export type Story = {
  frames: StoryFrame[];
  interaction?: { frame: number; question: string; options: string[]; answer: string };
};

export type LearningPack = {
  lesson: LessonItem[];
  order_game: { instruction: string; steps: string[] } | null;
  quiz_l1: QuizItem[];
  quiz_l2: QuizItem[];
  try_it: string;
  takeaway: string;
  source: string;
  story: Story | null;
};

export type NoorResponse = {
  status: AskStatus;
  question: string;
  topic: string | null;
  cached: boolean;
  pack: LearningPack; // the backend sends null when status != "ok"; noorApi.ts turns it into an empty pack
  passages: Passage[];
  referral: null | { reason: string; offline?: boolean };
};

export type ChildProfile = {
  name: string;
  age: number;
  focusMode: boolean;
  sessionLength: 3 | 5 | 8;
  sound: boolean;
  speechRate: number;
};

export type HistoryItem = {
  id: string;
  date: string;
  status: "answered" | "referred";
  response: NoorResponse;
  stars: number;
  durationMinutes: number;
};

export type NoorState = {
  child: ChildProfile;
  history: HistoryItem[];
  mastery: Record<string, number>;
  decisions: string[];
};