export interface Me {
  account: {
    id: number;
    email: string;
    displayName: string | null;
    isPlatformOwner: boolean;
  };
  studyProfile: {
    id: number;
    selectedLevel: string | null;
    estimatedLevel: string | null;
    operationalLevel: string | null;
  };
  levels: { all: string[]; available: string[] };
  classes: {
    inProgress: number;
    awaitingEvaluation: number;
    generationFailed: number;
    completed: number;
  };
  ai: { connections: number; available: number };
}

export interface AuthConfig {
  googleClientId: string | null;
  devLoginEnabled: boolean;
}

export interface TokenResponse {
  accessToken: string;
}

export interface ProviderInfo {
  key: string;
  label: string;
  defaultModel: string;
  requiresKey: boolean;
  supportsAudioInput: boolean;
}

export type ConnectionScope = 'account' | 'platform';

export interface AiEngineTrace {
  connectionId: number;
  connection: string;
  provider: string;
  providerLabel: string;
  model: string;
}

export interface ActiveAiConnections {
  default: AiEngineTrace | null;
  audio: AiEngineTrace | null;
}

export interface AiConnection {
  id: number;
  scope: ConnectionScope;
  provider: string;
  name: string;
  model: string;
  credentialHint: string | null;
  priority: number;
  active: boolean;
  status: string;
  usable: boolean;
  backoffUntil: string | null;
  lastCheckAt: string | null;
  lastUsedAt: string | null;
  lastErrorCode: string | null;
  dailyRequestLimit: number | null;
  perAccountDailyLimit: number | null;
  usage24h: number | null;
  supportsAudioInput: boolean;
  test?: { ok: boolean; error: string | null };
}

export type ClassStatus =
  | 'GENERATING'
  | 'GENERATION_FAILED'
  | 'READY'
  | 'IN_PROGRESS'
  | 'AWAITING_EVALUATION'
  | 'COMPLETED';

export type SessionKind = 'CLASS' | 'EXAM';

export interface ClassSummary {
  id: number;
  kind: SessionKind;
  title: string | null;
  status: ClassStatus;
  targetLevel: string | null;
  score: number | null;
  currentAttempt: number;
  createdAt: string;
  total: number;
  answered: number;
}

export interface ExerciseResult {
  score: number;
  result: 'correct' | 'partially_correct' | 'incorrect' | null;
  feedback: string | null;
  correctAnswer: string | null;
  errors: { type: string; fragment: string | null; correction: string | null; explanation: string; occurrences?: number }[];
  suggestions: { type: string; text: string }[];
  conceptResults: { concept: string; status: string }[];
  evaluationSource: string | null;
  ai: AiEngineTrace | null;
  appeal: { accepted: boolean; feedback?: string } | null;
  canAppeal: boolean;
}

export interface PronunciationResult {
  score: number;
  words: { word: string; score: number }[];
  phonemes: { phoneme: string; word: string; score: number }[];
  fluency: number | null;
  provider: string;
  providerLabel?: string;
  model?: string | null;
  connection?: string | null;
  /** true: estimación de la IA que transcribe (no medición acústica). */
  estimated?: boolean;
  assessedAt: string;
}

export interface Exercise {
  id: number;
  position: number;
  type:
    | 'fill_blank'
    | 'multiple_choice'
    | 'reading_multiple_choice'
    | 'rewrite'
    | 'short_writing';
  area: string | null;
  skillKey: string | null;
  skillName: string | null;
  instruction: string | null;
  question: string;
  passage: string | null;
  /** Modalidades (T-025): el tipo no cambia; cambia cómo se presenta y cómo se responde. */
  presentation: 'READ' | 'LISTEN';
  response: 'WRITE' | 'SELECT' | 'SPEAK';
  /** LISTEN: se sintetiza con voz y el texto se muestra recién tras la corrección. */
  stimulus: { mode: 'READ' | 'LISTEN'; text: string; lang: string; rate: number } | null;
  options: string[] | null;
  answer: string;
  audioDurationMs: number | null;
  pronunciationResult: PronunciationResult | null;
  assistance: Assistance;
  /** Señales de la respuesta (T-034): escuchas, uso de lento, prácticas de pronunciación. */
  signals: { listenPlays?: number; listenSlowPlays?: number; practiceScores?: number[]; speakRetakes?: number };
  hasLesson: boolean;
  result: ExerciseResult | null;
}

export type Assistance = 'NONE' | 'HINT' | 'LESSON';

export interface Lesson {
  skillKey: string;
  topic: string | null;
  skill: string | null;
  title: string;
  explanation: string;
  rules: string[];
  examples: { en: string; es: string }[];
  commonMistakes: { wrong: string; right: string; why: string }[];
  tip: string | null;
}

export interface LessonResponse {
  exerciseId: number;
  registered: boolean;
  lesson: Lesson;
}

export interface ClassDetail {
  id: number;
  kind: SessionKind;
  examResult: ExamResult | null;
  /** Habilidades que esta clase refuerza (T-034) y por qué. */
  focus: { key: string; kind: 'ability' | 'topic'; name: string; reason: string }[];
  certificateCode: string | null;
  title: string | null;
  status: ClassStatus;
  targetLevel: string | null;
  currentAttempt: number;
  score: number | null;
  createdAt: string;
  submittedAt: string | null;
  evaluatedAt: string | null;
  generationError: string | null;
  generatedBy: string | null;
  generationAi: AiEngineTrace | null;
  exercises: Exercise[];
  answered: number;
  history: { attempt: number; score: number }[];
  notice: string | null;
}

export interface SkillProgress {
  key: string;
  name: string;
  score: number | null;
  attemptCount: number;
  confidence: string;
  status: 'NOT_STARTED' | 'LEARNING' | 'MASTERED' | 'NEEDS_REVIEW';
  trend: string | null;
  assistedRecent: number;
}

export interface Dashboard {
  level: string;
  overallScore: number | null;
  skillsPracticed: number;
  skillsTotal: number;
  weakest: { key: string; name: string; score: number }[];
  areas: {
    key: string;
    name: string;
    score: number | null;
    attemptCount: number;
    topics: { key: string; name: string; score: number | null; skills: SkillProgress[] }[];
  }[];
  /** Progreso por habilidad del idioma (T-034): un ejercicio deja evidencia en varias. */
  abilities: AbilityProgress[];
}

export interface AbilityProgress {
  key: 'GRAMMAR' | 'VOCABULARY' | 'LISTENING' | 'SPEAKING' | 'PRONUNCIATION' | 'READING' | 'WRITING';
  name: string;
  score: number | null;
  evidenceCount: number;
  assistedCount: number;
  assistedRecent: number;
  trend: string | null;
  status: SkillProgress['status'];
  /** De qué temas vino la evidencia. */
  sources: { skillKey: string; name: string; count: number; score: number | null; assistedCount: number }[];
  practiceTrials?: number;
  practiceFirst?: number | null;
  practiceLast?: number | null;
}

export interface UsageCounts {
  requests: number;
  successful: number;
  errors: number;
}

export interface PlatformOverview {
  last24h: {
    all: UsageCounts;
    platform: UsageCounts;
    activeAccounts: number;
    classesCreated: number;
  };
  accounts: number;
  daily: { date: string; requests: number; platform: number; errors: number }[];
  connections: { id: number; name: string; last24h: UsageCounts; last30d: UsageCounts }[];
  topAccounts24h: { email: string; requests: number }[];
}

export interface ConnectionDraft {
  provider: string;
  name: string;
  model: string | null;
  apiKey: string | null;
  priority: number;
  scope: ConnectionScope;
  dailyRequestLimit?: number | null;
  perAccountDailyLimit?: number | null;
}

export interface ModelOption {
  id: string;
  label: string;
}

export interface ExamArea {
  key: string;
  name: string;
  score: number;
  items: number;
  passed: boolean;
}

export interface ExamResult {
  passed: boolean;
  score: number;
  passScore: number;
  areaMinScore: number;
  areas: ExamArea[];
  modalities?: ExamArea[];
}

export interface ExamCheck {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
}

export interface ExamProgress {
  practiced: number;
  total: number;
  coveragePercent: number;
  previewCoveragePercent: number;
  requiredCoveragePercent: number;
  previewNeeded: number;
  requiredNeeded: number;
  averageScore: number | null;
  requiredAverageScore: number;
}

export interface ExamStatus {
  level: string | null;
  available: boolean;
  showProposal?: boolean;
  progress?: ExamProgress;
  eligible?: boolean;
  checks?: ExamCheck[];
  passed?: boolean;
  certificateCode?: string | null;
  openExamId?: number | null;
  lastExam?: { id: number; score: number | null; result: ExamResult | null; evaluatedAt: string | null } | null;
  attempts?: number;
  cooldownUntil?: string | null;
  canStart?: boolean;
  nextLevel?: { level: string; available: boolean } | null;
  rules?: { passScore: number; areaMinScore: number; exercises: number; retryHours: number };
}

export interface Certificate {
  code: string;
  holderName: string;
  level: string;
  levelName: string | null;
  score: number;
  areaScores: Record<string, number>;
  issuedAt: string;
  issuer: string;
  notice: string;
}
