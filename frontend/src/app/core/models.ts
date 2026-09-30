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
}

export type ConnectionScope = 'account' | 'platform';

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
  test?: { ok: boolean; error: string | null };
}

export type ClassStatus =
  | 'GENERATING'
  | 'GENERATION_FAILED'
  | 'READY'
  | 'IN_PROGRESS'
  | 'AWAITING_EVALUATION'
  | 'COMPLETED';

export interface ClassSummary {
  id: number;
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
  errors: { type: string; fragment: string | null; correction: string | null; explanation: string }[];
  suggestions: { type: string; text: string }[];
  conceptResults: { concept: string; status: string }[];
  evaluationSource: string | null;
  appeal: { accepted: boolean; feedback?: string } | null;
  canAppeal: boolean;
}

export interface Exercise {
  id: number;
  position: number;
  type: 'fill_blank' | 'multiple_choice' | 'reading_multiple_choice' | 'rewrite' | 'short_writing';
  area: string | null;
  skillKey: string | null;
  skillName: string | null;
  instruction: string | null;
  question: string;
  passage: string | null;
  options: string[] | null;
  answer: string;
  result: ExerciseResult | null;
}

export interface ClassDetail {
  id: number;
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
