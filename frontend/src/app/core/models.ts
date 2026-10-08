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
  ai: { connections: number; available: number; own: number };
  service: MyService;
}

/** Servicio vigente de la cuenta (T-004): vínculo × fuente de IA. */
export type AiSource = 'BYOK' | 'PLATFORM' | 'HYBRID';
export type LinkType = 'PERSONAL' | 'CORPORATE';

export interface ServiceStatus {
  name: string;
  code: string | null;
  source: AiSource;
  linkType: LinkType;
  granted: boolean;
  origin: 'MANUAL' | 'CAMPAIGN' | 'INVITATION' | 'PAYMENT' | null;
  benefitId: number | null;
  benefitName: string | null;
  expiresAt: string | null;
  /** Rol de las keys propias: required (BYOK) · optional (Híbrido) · unused (Plataforma). */
  ownKeys: 'required' | 'optional' | 'unused';
  expired: { name: string; at: string } | null;
}

export interface MyService extends ServiceStatus {
  usesOwnKeys: boolean;
  usesPlatform: boolean;
}

export interface PlatformService {
  id: number;
  code: string;
  name: string;
  source: AiSource;
  linkType: LinkType;
  description: string | null;
  active: boolean;
  activeAccounts: number;
  activeBenefits: number;
  activeCampaigns: number;
  activeInvitations: number;
  canDisable: boolean;
}

export type PlatformServiceDraft = Pick<PlatformService, 'active'>;

export interface PlatformAccount {
  id: number;
  email: string;
  displayName: string | null;
  isPlatformOwner: boolean;
  createdAt: string;
  firstLoginAt: string | null;
  devPurgeAllowed: boolean;
  ownConnections: number;
  platformRequests24h: number;
  service: ServiceStatus;
  /** Cómo recibió el beneficio vigente: campaña, invitación o manual (null = sin beneficio). */
  channel: { type: 'CAMPAIGN' | 'INVITATION' | 'MANUAL' | 'PAYMENT' | null; name: string | null } | null;
}

export interface PlatformBenefit {
  id: number;
  code: string;
  name: string;
  /** Id interno de la combinación Servicio × Fuente. */
  serviceId: number;
  combinationId: number;
  service: LinkType;
  serviceName: string;
  source: AiSource;
  combinationName: string;
  combinationActive: boolean;
  durationDays: number | null;
  conflictPolicy: 'EXTEND_SAME_SERVICE';
  active: boolean;
  usedByCampaigns: number;
  usedByInvitations: number;
  activeBeneficiaries: number;
  activeCampaigns: number;
  activeInvitations: number;
  canDelete: boolean;
}

export interface PlatformBenefitDraft {
  name: string;
  service: LinkType;
  source: AiSource;
  durationDays: number | null;
  active: boolean;
}

export type CampaignStatus = 'DRAFT' | 'ACTIVE' | 'PAUSED' | 'ENDED';
export type CampaignTrigger = 'FIRST_LOGIN' | 'LOGIN' | 'SCHEDULED';
export type CampaignNotification = 'NONE' | 'IN_APP' | 'EMAIL' | 'IN_APP_EMAIL';
export type CampaignAction =
  | 'GRANT_BENEFIT'
  | 'SEND_NOTIFICATION'
  | 'GENERATE_REPORT'
  | 'CREATE_INVITATION'
  | 'APPLY_DISCOUNT';

export interface CampaignRule {
  field: string;
  subject?: string | null;
  filters?: Record<string, string>;
  operator: string;
  value: string | number | boolean;
  windowDays?: number | null;
}

export interface PlatformCampaign {
  id: number;
  code: string;
  name: string;
  benefitId: number;
  benefitName: string;
  action: CampaignAction;
  actionConfig: Record<string, unknown>;
  serviceId: number | null;
  serviceName: string;
  grantDays: number | null;
  status: CampaignStatus;
  trigger: CampaignTrigger;
  rules: CampaignRule[];
  priority: number;
  stackable: boolean;
  maxRecipients: number | null;
  recipients: number;
  startsAt: string | null;
  endsAt: string | null;
  activatedAt?: string | null;
  notification: CampaignNotification;
  message: string | null;
  pendingEmails: number;
  overlapWarnings: { id: number; name: string; priority: number; stackable: boolean }[];
}

export interface PlatformCampaignDraft {
  name: string;
  benefitId: number;
  action: CampaignAction;
  actionConfig: Record<string, unknown>;
  trigger: CampaignTrigger;
  rules: CampaignRule[];
  priority: number;
  stackable: boolean;
  maxRecipients: number | null;
  startsAt: string | null;
  endsAt: string | null;
  notification: CampaignNotification;
  message: string | null;
}

export interface CampaignAssistDraft {
  name: string;
  benefitId: number | null;
  action: CampaignAction;
  actionConfig: Record<string, unknown>;
  trigger: CampaignTrigger;
  rules: CampaignRule[];
  priority: number;
  stackable: boolean;
  maxRecipients: number | null;
  startsAt: string | null;
  endsAt: string | null;
  notification: CampaignNotification;
  message: string | null;
}

export interface CampaignAssistRequirement {
  text: string;
  kind: 'RULE' | 'TRIGGER' | 'ACTION' | 'DELIVERY' | 'BENEFIT' | 'LIMIT' | 'DATE' | 'UNKNOWN';
  status: 'REPRESENTED' | 'UNSUPPORTED' | 'INVALID';
  capability: string | null;
  verified: boolean;
  reason: string | null;
}

export interface CampaignAssistResult {
  draft: CampaignAssistDraft;
  requirements: CampaignAssistRequirement[];
  warnings: string[];
  blockingIssues: string[];
  executable: boolean;
  summary: string;
}


export interface CampaignRuleFilterCapability {
  key: string;
  label: string;
  valueType: 'enum' | 'string';
  options: { value: string; label: string }[];
  required: boolean;
}

export interface CampaignRuleCapability {
  key: string;
  label: string;
  valueType: 'boolean' | 'integer' | 'number' | 'datetime' | 'enum' | 'string';
  operators: string[];
  description: string;
  options: { value: string; label: string }[];
  subjectLabel: string | null;
  subjectOptions: { value: string; label: string }[];
  filters: CampaignRuleFilterCapability[];
  available: boolean;
  requiresWindow: boolean;
  windowMinDays: number | null;
  windowMaxDays: number | null;
}

export interface CampaignChoiceCapability {
  key: string;
  label: string;
  available: boolean;
  description: string;
  requiresBenefit?: boolean;
}

export interface PlatformCampaignCapabilities {
  rules: CampaignRuleCapability[];
  triggers: CampaignChoiceCapability[];
  actions: CampaignChoiceCapability[];
  deliveries: CampaignChoiceCapability[];
}

export type CampaignPolicyKind = 'SUPPRESSION' | 'EXCLUSION';
export type CampaignPolicyEffect = 'BLOCK';
export type CampaignPolicyAppliesToMode = 'ALL' | 'CAMPAIGNS';

export interface CampaignPolicyRule {
  field: string;
  operator: string;
  value: number;
  windowDays: number;
}

export interface CampaignPolicyAppliesTo {
  mode: CampaignPolicyAppliesToMode;
  campaignIds: number[];
}

export interface PlatformCampaignPolicy {
  id: number;
  name: string;
  description: string | null;
  kind: CampaignPolicyKind;
  effect: CampaignPolicyEffect;
  enabled: boolean;
  appliesTo: CampaignPolicyAppliesTo;
  rules: CampaignPolicyRule[];
  blockCount: number;
  lastBlockedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PlatformCampaignPolicyDraft {
  name: string;
  description: string | null;
  kind: CampaignPolicyKind;
  enabled: boolean;
  appliesTo: CampaignPolicyAppliesTo;
  rules: CampaignPolicyRule[];
}

export interface CampaignPolicyChoiceCapability {
  key: string;
  label: string;
  available: boolean;
  description: string;
}

export interface CampaignPolicyRuleCapability {
  key: string;
  label: string;
  valueType: 'integer';
  operators: string[];
  description: string;
  requiresWindow: boolean;
  windowMinDays: number | null;
  windowMaxDays: number | null;
  available: boolean;
}

export interface PlatformCampaignPolicyCapabilities {
  kinds: CampaignPolicyChoiceCapability[];
  effects: CampaignPolicyChoiceCapability[];
  rules: CampaignPolicyRuleCapability[];
  conditionModes: CampaignPolicyChoiceCapability[];
  appliesToModes: CampaignPolicyChoiceCapability[];
}

export interface CampaignPolicyBlock {
  id: number;
  policyId: number;
  policy: string;
  kind: CampaignPolicyKind;
  campaignId: number;
  campaign: string;
  accountId: number;
  account: string;
  reason: string;
  createdAt: string;
}

export interface CampaignPolicyAssistRequirement {
  text: string;
  kind: 'TYPE' | 'SCOPE' | 'RULE' | string;
  status: 'REPRESENTED' | 'UNSUPPORTED';
  capability: string | null;
  reason: string | null;
  verified: boolean;
}

export interface CampaignPolicyAssistResult {
  draft: PlatformCampaignPolicyDraft;
  requirements: CampaignPolicyAssistRequirement[];
  warnings: string[];
  blockingIssues: string[];
  executable: boolean;
  summary: string;
}

export interface CampaignAudienceRuleResult {
  field: string;
  operator: string;
  expected: string | number | boolean;
  actual: string | number | boolean | null;
  subject?: string | null;
  filters?: Record<string, string>;
  matched: boolean;
  windowDays?: number | null;
}

export interface CampaignAudienceSample {
  accountId: number;
  email: string;
  displayName: string | null;
  eligible: boolean;
  alreadyReceived: boolean;
  triggerMatch: boolean;
  rules: CampaignAudienceRuleResult[];
}

export interface CampaignAudiencePreview {
  candidateCount: number;
  eligibleCount: number;
  excludedCount: number;
  sample: CampaignAudienceSample[];
  warnings: string[];
  action: CampaignAction;
}

export type InvitationRecipientMode = 'NAMED' | 'OPEN';
export type InvitationStatus = 'ACTIVE' | 'CANCELLED' | 'EXPIRED' | 'EXHAUSTED';

export interface PlatformInvitation {
  id: number;
  name: string;
  benefitId: number | null;
  benefitName: string;
  serviceName: string;
  durationDays: number | null;
  recipientMode: InvitationRecipientMode;
  email: string | null;
  firstName: string | null;
  lastName: string | null;
  status: InvitationStatus;
  maxRedemptions: number;
  redemptions: number;
  remaining: number;
  expiresAt: string | null;
  emailStatus: string | null;
  token: string | null;
  createdAt: string;
}

export interface PlatformInvitationDraft {
  name: string;
  benefitId: number;
  recipientMode: InvitationRecipientMode;
  email: string | null;
  firstName: string | null;
  lastName: string | null;
  maxRedemptions: number;
  expiresAt: string | null;
}

export interface InvitationPreview {
  name: string;
  recipientMode: InvitationRecipientMode;
  recipientEmailHint: string | null;
  benefitName: string;
  serviceName: string;
  durationDays: number | null;
  status: InvitationStatus;
  remaining: number;
  expiresAt: string | null;
}

export interface InvitationRedemption {
  invitation: string;
  benefit: string;
  alreadyRedeemed: boolean;
  redeemedAt: string;
}

export interface CampaignNotice {
  grantId: number;
  campaignId: number;
  campaign: string;
  message: string;
  benefit: string;
  appliedAt: string;
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

/** Traza del motor de IA. Si es de plataforma y no sos el dueño, llega como
 *  "IA de Librería Inglés", sin connectionId ni motor (T-055). */
export interface AiEngineTrace {
  connectionId: number | null;
  connection: string;
  provider: string;
  providerLabel: string;
  model: string;
  ownerType?: 'ACCOUNT' | 'PLATFORM' | 'ORGANIZATION';
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
  /** T-191: límites del proveedor aprendidos solos (del rechazo o de los headers). */
  learnedLimits?: LearnedLimit[];
  test?: { ok: boolean; error: string | null };
}

export interface LearnedLimit {
  kind: 'RENEWABLE' | 'EXHAUSTED';
  dimension: 'REQUESTS' | 'TOKENS' | 'INPUT_TOKENS' | 'OUTPUT_TOKENS';
  window: 'MINUTE' | 'DAY' | 'MONTH';
  limit: number | null;
  used: number | null;
  resetAt: string | null;
  source: 'HEADER' | 'ERROR' | 'ESTIMATED';
  tier: string | null;
  observedAt: string | null;
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
  secondarySkillResults: { skillKey: string; status: string; score: number; reason: string }[];
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
  /** T-216: reportes que hizo este alumno sobre el ejercicio. */
  reported?: ('REPEATED' | 'WRONG')[];
  /** T-214: tanda de la práctica continua (1 en clases clásicas). */
  batch?: number;
  id: number;
  position: number;
  type:
    | 'fill_blank'
    | 'multiple_choice'
    | 'reading_multiple_choice'
    | 'rewrite'
    | 'short_writing'
    | 'conversation'
    // T-183: tipos nuevos de A1.
    | 'dictation'
    | 'word_order'
    | 'dialogue_choice'
    | 'read_aloud'
    | 'minimal_pairs'
    | 'match_pairs'
    | 'listen_form'
    | 'gap_text'
    | 'error_correction'
    | 'word_stress';
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
  /** T-048: dos ejercicios enlazados forman una microconversación. */
  conversation: { group: string; turn: number; total: number; closing: string | null } | null;
  /** T-183: fichas mezcladas (word_order), columnas (match_pairs) y campos (listen_form). */
  tiles?: string[] | null;
  pairs?: { left: string[]; right: string[] } | null;
  fields?: string[] | null;
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
  /** T-191: la clase se generó con menos ejercicios por falta de cupo de IA. */
  reducedFrom?: number | null;
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
  /** T-214: práctica continua por tandas (null en la clase clásica y el examen). */
  practice?: { batch: number; batchSize: number; finished: boolean } | null;
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
  /** Ortografía vive dentro de Writing pero tiene indicador explícito (T-048). */
  orthography: {
    name: string;
    score: number | null;
    skillsPracticed: number;
    skillsTotal: number;
    attemptCount: number;
    assistedRecent: number;
    status: SkillProgress['status'];
  };
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

export type AiUsageScopeKind = 'ME' | 'ORGANIZATION' | 'PLATFORM';

export interface AiUsageScope {
  kind: AiUsageScopeKind;
  id: number | null;
  label: string;
}

export interface AiUsageSubject {
  type: string | null;
  id: number | null;
  label: string | null;
  route: string | null;
  classId: number | null;
  exerciseNumber: number | null;
  previewable: boolean;
}

export interface AiUsageExecution {
  id: string;
  attempt: number | null;
  attempts: number;
  status: 'OK' | 'RECOVERED_BY_FAILOVER' | 'INTERRUPTED';
}

export interface AiUsageRow {
  id: number;
  createdAt: string;
  accountId: number | null;
  accountEmail: string | null;
  accountName: string | null;
  organizationId: number | null;
  operation: string;
  provider: string;
  model: string | null;
  connectionName: string | null;
  connectionRoute: string | null;
  connectionId: number | null;
  connectionOwnerType: 'ACCOUNT' | 'PLATFORM' | 'ORGANIZATION';
  serviceSource: AiSource | 'OWNER' | null;
  actualSource: 'BYOK' | 'PLATFORM' | 'ORGANIZATION';
  inputTokens: number | null;
  reasoningTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
  success: boolean;
  errorCode: string | null;
  execution: AiUsageExecution | null;
  subject: AiUsageSubject | null;
}


export interface AiUsageDiagnosticSnapshot {
  version: number;
  requestKind: 'TEXT_JSON' | 'AUDIO' | string;
  systemChars?: number;
  userChars?: number;
  systemFingerprint?: string;
  responseJsonChars?: number;
  transcriptChars?: number;
  audioBytes?: number;
  mimeType?: string;
  details?: Record<string, unknown>;
}

export interface AiUsageDiagnosticMetric {
  key: string;
  label: string;
  value: number;
  median: number;
  ratio: number | null;
  sampleSize: number;
}

export interface AiUsageDiagnosticResponse {
  eventId: number;
  operation: string;
  createdAt: string;
  subject: Omit<AiUsageSubject, 'route'> | null;
  execution: AiUsageExecution | null;
  diagnostic: {
    tokens: {
      input: number | null;
      reasoning: number | null;
      output: number | null;
      total: number | null;
    };
    snapshot: AiUsageDiagnosticSnapshot | null;
    comparison: {
      sampleSize: number;
      enoughSample: boolean;
      medianTotalTokens: number | null;
      p90TotalTokens: number | null;
      totalVsMedian: number | null;
      cohort: {
        operation: string;
        subjectType: string | null;
        provider: string;
        model: string | null;
        exerciseType: string | null;
        promptFingerprint: string | null;
      };
      metrics: AiUsageDiagnosticMetric[];
      signals: AiUsageDiagnosticMetric[];
    };
    note: string;
  };
}

export interface AiUsageExecutionContext {
  operation: string;
  presentationMode: string;
  responseMode: string;
  evaluationMode: string;
  evaluationSource: string | null;
  audioDurationMs: number | null;
  listenPlays: number;
  listenSlowPlays: number;
  speakRetakes: number;
  pronunciationPracticeScores: number[];
  pronunciationEvaluated: boolean;
  assistance: string;
  contextStats: {
    instructionChars: number;
    questionChars: number;
    passageChars: number;
    answerChars: number;
    options: number;
    expectedConcepts: number;
  };
}

export interface AiUsageReferenceExercise {
  id: number;
  number: number;
  type: string;
  area: string | null;
  skillKey?: string | null;
  instruction: string | null;
  question: string;
  passage: string | null;
  options?: string[] | null;
  conversation: { turn?: number; total?: number; closing?: string } | null;
  presentation?: string;
  responseMode?: string;
  answer: string | null;
  score: number | null;
  result?: string | null;
  feedback: string | null;
  correctAnswer?: string | null;
  executionContext?: AiUsageExecutionContext;
}

export interface AiUsageReference {
  eventId: number;
  kind: 'EXERCISE' | 'CLASS';
  operation?: string;
  class: {
    id: number;
    kind: 'CLASS' | 'EXAM';
    label: string;
    title: string | null;
    targetLevel: string | null;
    status?: string;
    score?: number | null;
  };
  exercise?: AiUsageReferenceExercise;
  exercises?: AiUsageReferenceExercise[];
  generationSummary?: {
    logicalExercises: number;
    storedExerciseRows: number;
    types: Record<string, number>;
    presentationModes: Record<string, number>;
    responseModes: Record<string, number>;
  };
  fullClassRoute: string | null;
}

export interface AiUsageReport {
  scope: AiUsageScopeKind;
  organizationId: number | null;
  scopes: AiUsageScope[];
  summary: {
    executions: number;
    requests: number;
    successful: number;
    errors: number;
    measuredRequests: number;
    inputTokens: number;
    reasoningTokens: number;
    outputTokens: number;
    totalTokens: number;
  };
  offset: number;
  limit: number;
  total: number;
  rows: AiUsageRow[];
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
  benefitUsage: { id: number; name: string; campaigns: number; invitations: number }[];
  accountBenefits: {
    email: string;
    benefitName: string;
    serviceName: string;
    origin: 'MANUAL' | 'CAMPAIGN' | 'INVITATION' | 'PAYMENT';
    expiresAt: string | null;
  }[];
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
  dimensions?: ExamArea[];
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


export type OrganizationActingCapacity =
  | 'LEGAL_REPRESENTATIVE'
  | 'PROXY'
  | 'AUTHORIZED_EMPLOYEE'
  | 'OTHER';

export interface OrganizationOnboardingConfig {
  countries: Array<{
    code: string;
    name: string;
    taxIdTypes: Array<{ code: string; name: string }>;
  }>;
  actingCapacities: Array<{ code: OrganizationActingCapacity; name: string }>;
  emailVerificationImplemented: boolean;
  devPurgeAllowed: boolean;
}

export interface OrganizationCompanyLookupRequest {
  country: string;
  taxIdType: string;
  taxId: string;
}

export interface OrganizationCompanyLookupResult {
  state: 'VERIFIED' | 'PENDING' | 'REVIEW_REQUIRED';
  country: string;
  taxIdType: string;
  taxId: string;
  source: string;
  message: string;
  checkedAt: string;
  developmentSimulation: boolean;
  company: {
    legalName: string | null;
    legalEntityType: string | null;
    registryJurisdiction: string | null;
    registryNumber: string | null;
    fiscalAddress: string | null;
    legalAddress: string | null;
    primaryActivity: string | null;
  };
  platform: {
    alreadyRegistered: boolean;
    onboardingInProgress: boolean;
    onboardingPublicId: string | null;
  };
}

export interface OrganizationOnboardingDraft extends OrganizationCompanyLookupRequest {
  displayName: string | null;
  website: string | null;
  referent: {
    firstName: string;
    lastName: string;
    email: string;
    jobTitleId: number | null;
    jobTitle: string;
    phone: string;
    actingCapacity: OrganizationActingCapacity;
    authorityDeclared: boolean;
  };
}

export interface OrganizationOnboardingResult {
  publicId: string;
  status:
    | 'DRAFT'
    | 'COMPANY_VERIFIED'
    | 'VERIFICATION_PENDING'
    | 'REVIEW_REQUIRED'
    | 'ABANDONED'
    | 'PROVISIONED';
  company: {
    country: string;
    taxIdType: string;
    taxId: string;
    legalName: string | null;
    displayName: string | null;
    legalEntityType: string | null;
    registryJurisdiction: string | null;
    registryNumber: string | null;
    fiscalAddress: string | null;
    legalAddress: string | null;
    primaryActivity: string | null;
    website: string | null;
  };
  referent: {
    firstName: string;
    lastName: string;
    email: string;
    jobTitleId: number | null;
    jobTitle: string;
    phone: string;
    actingCapacity: OrganizationActingCapacity;
    emailVerified: boolean;
  };
  verification: {
    source: string | null;
    message: string | null;
    checkedAt: string | null;
    developmentSimulation: boolean;
  };
  nextStep:
    | 'EMAIL_VERIFICATION_PENDING_P02'
    | 'COMPANY_VERIFICATION_PENDING'
    | 'MANUAL_REVIEW_REQUIRED';
}


export interface OrganizationOnboardingDevPurgeResult {
  country: string;
  taxIdType: string;
  taxId: string;
  deletedOnboardings: number;
}


export interface JobTitleOption {
  id: number;
  name: string;
  score?: number;
}

export interface JobTitleResolveResult {
  status: 'EXISTING' | 'CREATED' | 'SIMILAR';
  item: JobTitleOption | null;
  similar: JobTitleOption[];
}
