import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  ActiveAiConnections,
  AiConnection,
  AiUsageDiagnosticResponse,
  AiUsageReference,
  AiUsageReport,
  AiUsageScope,
  AiUsageScopeKind,
  AuthConfig,
  Certificate,
  CampaignAssistResult,
  CampaignAudiencePreview,
  CampaignNotice,
  CampaignPolicyAssistResult,
  CampaignPolicyBlock,
  ClassDetail,
  ClassSummary,
  ConnectionDraft,
  ConnectionScope,
  Dashboard,
  ExamStatus,
  Exercise,
  LessonResponse,
  Me,
  ModelOption,
  OrganizationCompanyLookupRequest,
  OrganizationCompanyLookupResult,
  OrganizationOnboardingConfig,
  OrganizationOnboardingDraft,
  OrganizationOnboardingDevPurgeResult,
  OrganizationOnboardingResult,
  InvitationPreview,
  InvitationRedemption,
  JobTitleOption,
  JobTitleResolveResult,
  PlatformAccount,
  PlatformBenefit,
  PlatformBenefitDraft,
  PlatformCampaign,
  PlatformCampaignCapabilities,
  PlatformCampaignDraft,
  PlatformCampaignPolicy,
  PlatformCampaignPolicyCapabilities,
  PlatformCampaignPolicyDraft,
  PlatformInvitation,
  PlatformInvitationDraft,
  PlatformOverview,
  PlatformService,
  PlatformServiceDraft,
  ProviderInfo,
  TokenResponse
} from './models';

export function errorMessage(error: unknown, fallback = 'Ocurrió un error inesperado.'): string {
  if (error instanceof HttpErrorResponse) {
    if (error.status === 0) {
      return 'No se pudo conectar con el backend.';
    }
    const detail = error.error?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail) && detail[0]?.msg) {
      return detail[0].msg;
    }
  }
  return fallback;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiUrl;

  // Alta corporativa P01
  organizationOnboardingConfig(): Observable<OrganizationOnboardingConfig> {
    return this.http.get<OrganizationOnboardingConfig>(
      `${this.base}/organization-onboarding/config`
    );
  }

  organizationJobTitles(query = '', limit = 8): Observable<JobTitleOption[]> {
    return this.http.get<JobTitleOption[]>(
      `${this.base}/organization-onboarding/job-titles`,
      { params: { q: query, limit } }
    );
  }

  resolveOrganizationJobTitle(
    name: string,
    confirmSimilar = false
  ): Observable<JobTitleResolveResult> {
    return this.http.post<JobTitleResolveResult>(
      `${this.base}/organization-onboarding/job-titles/resolve`,
      { name, confirmSimilar }
    );
  }

  lookupOrganizationCompany(
    draft: OrganizationCompanyLookupRequest
  ): Observable<OrganizationCompanyLookupResult> {
    return this.http.post<OrganizationCompanyLookupResult>(
      `${this.base}/organization-onboarding/company/lookup`,
      draft
    );
  }

  createOrganizationOnboarding(
    draft: OrganizationOnboardingDraft
  ): Observable<OrganizationOnboardingResult> {
    return this.http.post<OrganizationOnboardingResult>(
      `${this.base}/organization-onboarding`,
      draft
    );
  }

  purgeOrganizationOnboardingDev(
    country: string,
    taxIdType: string,
    taxId: string
  ): Observable<OrganizationOnboardingDevPurgeResult> {
    return this.http.delete<OrganizationOnboardingDevPurgeResult>(
      `${this.base}/organization-onboarding/dev-purge`,
      { params: { country, taxIdType, taxId } }
    );
  }

  // Auth
  authConfig(): Observable<AuthConfig> {
    return this.http.get<AuthConfig>(`${this.base}/auth/config`);
  }

  loginGoogle(credential: string, invitationToken: string | null = null): Observable<TokenResponse> {
    return this.http.post<TokenResponse>(`${this.base}/auth/google`, { credential, invitationToken });
  }

  loginDev(
    email: string,
    name: string | null,
    invitationToken: string | null = null
  ): Observable<TokenResponse> {
    return this.http.post<TokenResponse>(`${this.base}/auth/dev-login`, {
      email,
      name,
      invitationToken
    });
  }

  me(): Observable<Me> {
    return this.http.get<Me>(`${this.base}/me`);
  }

  setLevel(level: string): Observable<Me> {
    return this.http.put<Me>(`${this.base}/me/level`, { level });
  }

  // IA
  providers(): Observable<ProviderInfo[]> {
    return this.http.get<ProviderInfo[]>(`${this.base}/ai/providers`);
  }

  connections(scope: ConnectionScope = 'account'): Observable<AiConnection[]> {
    return this.http.get<AiConnection[]>(`${this.base}/ai/connections`, { params: { scope } });
  }

  activeAiConnections(): Observable<ActiveAiConnections> {
    return this.http.get<ActiveAiConnections>(`${this.base}/ai/active`);
  }

  aiUsageScopes(): Observable<AiUsageScope[]> {
    return this.http.get<AiUsageScope[]>(`${this.base}/ai/usage/scopes`);
  }

  aiUsage(
    scope: AiUsageScopeKind,
    organizationId: number | null = null,
    limit = 50,
    offset = 0
  ): Observable<AiUsageReport> {
    const params: Record<string, string | number> = { scope, limit, offset };
    if (scope === 'ORGANIZATION' && organizationId !== null) {
      params['organizationId'] = organizationId;
    }
    return this.http.get<AiUsageReport>(`${this.base}/ai/usage`, { params });
  }

  aiUsageReference(eventId: number, view: 'REFERENCE' | 'CLASS' = 'REFERENCE'): Observable<AiUsageReference> {
    return this.http.get<AiUsageReference>(`${this.base}/ai/usage/${eventId}/reference`, {
      params: { view }
    });
  }

  aiUsageDiagnostic(eventId: number): Observable<AiUsageDiagnosticResponse> {
    return this.http.get<AiUsageDiagnosticResponse>(`${this.base}/ai/usage/${eventId}/diagnostic`);
  }

  createConnection(body: ConnectionDraft): Observable<AiConnection> {
    return this.http.post<AiConnection>(`${this.base}/ai/connections`, body);
  }

  updateConnection(
    id: number,
    body: Partial<{
      name: string;
      model: string;
      apiKey: string;
      priority: number;
      active: boolean;
      dailyRequestLimit: number | null;
      perAccountDailyLimit: number | null;
    }>
  ): Observable<AiConnection> {
    return this.http.patch<AiConnection>(`${this.base}/ai/connections/${id}`, body);
  }

  listModels(provider: string, apiKey: string | null): Observable<ModelOption[]> {
    return this.http.post<ModelOption[]>(`${this.base}/ai/models`, { provider, apiKey });
  }

  connectionModels(id: number): Observable<ModelOption[]> {
    return this.http.get<ModelOption[]>(`${this.base}/ai/connections/${id}/models`);
  }

  copyConnectionCredential(id: number): Observable<{ apiKey: string }> {
    return this.http.post<{ apiKey: string }>(
      `${this.base}/ai/connections/${id}/credential/copy`,
      {}
    );
  }

  deleteConnection(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/ai/connections/${id}`);
  }

  testConnection(id: number): Observable<AiConnection> {
    return this.http.post<AiConnection>(`${this.base}/ai/connections/${id}/test`, {});
  }

  // Clases
  classes(): Observable<ClassSummary[]> {
    return this.http.get<ClassSummary[]>(`${this.base}/classes`);
  }

  createClass(): Observable<ClassDetail> {
    return this.http.post<ClassDetail>(`${this.base}/classes`, {});
  }

  /** T-214: "Nueva clase" = práctica continua por tandas. */
  createPractice(): Observable<ClassDetail> {
    return this.http.post<ClassDetail>(`${this.base}/classes/practice`, {});
  }

  continuePractice(classId: number, answers: Record<number, string>): Observable<ClassDetail> {
    return this.http.post<ClassDetail>(`${this.base}/classes/${classId}/continue`, { answers });
  }

  getClass(id: number): Observable<ClassDetail> {
    return this.http.get<ClassDetail>(`${this.base}/classes/${id}`);
  }

  saveAnswer(classId: number, exerciseId: number, answer: string): Observable<{ savedAt: string }> {
    return this.http.put<{ savedAt: string }>(
      `${this.base}/classes/${classId}/answers/${exerciseId}`,
      { answer }
    );
  }

  processSpeakingAnswer(
    classId: number,
    exerciseId: number,
    audio: Blob,
    durationMs: number
  ): Observable<{
    exerciseId: number;
    transcript: string;
    durationMs: number | null;
    savedAt: string;
    provider: string;
    ai: import('./models').AiEngineTrace;
    switched: boolean;
    pronunciationResult: import('./models').PronunciationResult | null;
  }> {
    return this.http.post<{
      exerciseId: number;
      transcript: string;
      durationMs: number | null;
      savedAt: string;
      provider: string;
      ai: import('./models').AiEngineTrace;
      switched: boolean;
      pronunciationResult: import('./models').PronunciationResult | null;
    }>(`${this.base}/classes/${classId}/answers/${exerciseId}/transcribe`, audio, {
      headers: {
        'Content-Type': audio.type || 'audio/webm',
        'X-Audio-Duration-Ms': String(durationMs)
      }
    });
  }

  submitClass(classId: number, answers: Record<number, string>): Observable<ClassDetail> {
    return this.http.post<ClassDetail>(`${this.base}/classes/${classId}/submit`, { answers });
  }

  retryGeneration(classId: number): Observable<ClassDetail> {
    return this.http.post<ClassDetail>(`${this.base}/classes/${classId}/retry-generation`, {});
  }

  retakeClass(classId: number): Observable<ClassDetail> {
    return this.http.post<ClassDetail>(`${this.base}/classes/${classId}/retake`, {});
  }

  // ---------------------------------------------------------------- examen de nivel (T-024)

  examStatus(): Observable<ExamStatus> {
    return this.http.get<ExamStatus>(`${this.base}/exams/status`);
  }

  createExam(): Observable<ClassDetail> {
    return this.http.post<ClassDetail>(`${this.base}/exams`, {});
  }

  /** Público: verificación del certificado por código. */
  certificate(code: string): Observable<Certificate> {
    return this.http.get<Certificate>(`${this.base}/certificates/${encodeURIComponent(code)}`);
  }

  /** Señal de la respuesta en curso (T-034): una escucha o un intento de práctica. */
  recordSignal(
    classId: number,
    exerciseId: number,
    signal: { kind: 'listen'; slow: boolean } | { kind: 'practice'; score: number } | { kind: 'retake' }
  ): Observable<{ exerciseId: number; signals: Exercise['signals'] }> {
    return this.http.post<{ exerciseId: number; signals: Exercise['signals'] }>(
      `${this.base}/classes/${classId}/exercises/${exerciseId}/signals`,
      signal
    );
  }

  /** "Necesito lección" (T-020): devuelve la lección y registra la ayuda si la clase está abierta. */
  lesson(classId: number, exerciseId: number): Observable<LessonResponse> {
    return this.http.post<LessonResponse>(
      `${this.base}/classes/${classId}/exercises/${exerciseId}/lesson`,
      {}
    );
  }

  /** T-216: "Este ejercicio se repite" / "Este ejercicio está mal". */
  reportExercise(classId: number, exerciseId: number, reason: 'REPEATED' | 'WRONG'): Observable<ClassDetail> {
    return this.http.post<ClassDetail>(`${this.base}/classes/${classId}/exercises/${exerciseId}/report`, { reason });
  }

  appeal(classId: number, exerciseId: number): Observable<ClassDetail> {
    return this.http.post<ClassDetail>(
      `${this.base}/classes/${classId}/exercises/${exerciseId}/appeal`,
      {}
    );
  }

  processPending(): Observable<{ pending: number; completed: number }> {
    return this.http.post<{ pending: number; completed: number }>(
      `${this.base}/classes/process-pending`,
      {}
    );
  }

  // Progreso
  progress(): Observable<Dashboard> {
    return this.http.get<Dashboard>(`${this.base}/progress`);
  }

  // Plataforma (PLATFORM_OWNER)
  platformOverview(): Observable<PlatformOverview> {
    return this.http.get<PlatformOverview>(`${this.base}/platform/overview`);
  }

  // Servicios (T-004)
  platformServices(): Observable<PlatformService[]> {
    return this.http.get<PlatformService[]>(`${this.base}/platform/services`);
  }

  updatePlatformService(id: number, draft: PlatformServiceDraft): Observable<PlatformService> {
    return this.http.put<PlatformService>(`${this.base}/platform/services/${id}`, draft);
  }

  platformAccounts(q: string): Observable<PlatformAccount[]> {
    return this.http.get<PlatformAccount[]>(`${this.base}/platform/accounts`, {
      params: q.trim() ? { q: q.trim() } : {}
    });
  }

  grantBenefit(accountId: number, benefitId: number): Observable<PlatformAccount> {
    return this.http.post<PlatformAccount>(`${this.base}/platform/accounts/${accountId}/benefit`, {
      benefitId
    });
  }

  revokeService(accountId: number): Observable<PlatformAccount> {
    return this.http.delete<PlatformAccount>(`${this.base}/platform/accounts/${accountId}/service`);
  }

  devPurgePlatformAccount(accountId: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/platform/accounts/${accountId}/dev-purge`);
  }

  // Beneficios reutilizables (T-004)
  platformBenefits(): Observable<PlatformBenefit[]> {
    return this.http.get<PlatformBenefit[]>(`${this.base}/platform/benefits`);
  }

  createPlatformBenefit(draft: PlatformBenefitDraft): Observable<PlatformBenefit> {
    return this.http.post<PlatformBenefit>(`${this.base}/platform/benefits`, draft);
  }

  updatePlatformBenefit(id: number, draft: PlatformBenefitDraft): Observable<PlatformBenefit> {
    return this.http.put<PlatformBenefit>(`${this.base}/platform/benefits/${id}`, draft);
  }

  deletePlatformBenefit(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/platform/benefits/${id}`);
  }

  // Campañas (T-004 etapa 2)
  platformCampaigns(): Observable<PlatformCampaign[]> {
    return this.http.get<PlatformCampaign[]>(`${this.base}/platform/campaigns`);
  }

  platformCampaignCapabilities(): Observable<PlatformCampaignCapabilities> {
    return this.http.get<PlatformCampaignCapabilities>(`${this.base}/platform/campaigns/capabilities`);
  }

  previewPlatformCampaign(draft: PlatformCampaignDraft): Observable<CampaignAudiencePreview> {
    return this.http.post<CampaignAudiencePreview>(`${this.base}/platform/campaigns/preview`, draft);
  }

  createPlatformCampaign(draft: PlatformCampaignDraft): Observable<PlatformCampaign> {
    return this.http.post<PlatformCampaign>(`${this.base}/platform/campaigns`, draft);
  }

  assistPlatformCampaign(description: string): Observable<CampaignAssistResult> {
    return this.http.post<CampaignAssistResult>(`${this.base}/platform/campaigns/assist`, {
      description
    });
  }

  updatePlatformCampaign(id: number, draft: PlatformCampaignDraft): Observable<PlatformCampaign> {
    return this.http.put<PlatformCampaign>(`${this.base}/platform/campaigns/${id}`, draft);
  }

  activatePlatformCampaign(id: number): Observable<PlatformCampaign> {
    return this.http.post<PlatformCampaign>(`${this.base}/platform/campaigns/${id}/activate`, {});
  }

  pausePlatformCampaign(id: number): Observable<PlatformCampaign> {
    return this.http.post<PlatformCampaign>(`${this.base}/platform/campaigns/${id}/pause`, {});
  }

  finishPlatformCampaign(id: number): Observable<PlatformCampaign> {
    return this.http.post<PlatformCampaign>(`${this.base}/platform/campaigns/${id}/finish`, {});
  }
  deletePlatformCampaign(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/platform/campaigns/${id}`);
  }

  // Políticas globales de Campaigns (T-141)
  platformCampaignPolicies(): Observable<PlatformCampaignPolicy[]> {
    return this.http.get<PlatformCampaignPolicy[]>(`${this.base}/platform/campaigns/policies`);
  }

  platformCampaignPolicyCapabilities(): Observable<PlatformCampaignPolicyCapabilities> {
    return this.http.get<PlatformCampaignPolicyCapabilities>(
      `${this.base}/platform/campaigns/policies/capabilities`
    );
  }

  platformCampaignPolicyBlocks(limit = 50): Observable<CampaignPolicyBlock[]> {
    return this.http.get<CampaignPolicyBlock[]>(
      `${this.base}/platform/campaigns/policies/blocks`,
      { params: { limit } }
    );
  }

  assistPlatformCampaignPolicy(description: string): Observable<CampaignPolicyAssistResult> {
    return this.http.post<CampaignPolicyAssistResult>(
      `${this.base}/platform/campaigns/policies/assist`,
      { description }
    );
  }

  createPlatformCampaignPolicy(
    draft: PlatformCampaignPolicyDraft
  ): Observable<PlatformCampaignPolicy> {
    return this.http.post<PlatformCampaignPolicy>(
      `${this.base}/platform/campaigns/policies`,
      draft
    );
  }

  updatePlatformCampaignPolicy(
    id: number,
    draft: PlatformCampaignPolicyDraft
  ): Observable<PlatformCampaignPolicy> {
    return this.http.put<PlatformCampaignPolicy>(
      `${this.base}/platform/campaigns/policies/${id}`,
      draft
    );
  }

  enablePlatformCampaignPolicy(id: number): Observable<PlatformCampaignPolicy> {
    return this.http.post<PlatformCampaignPolicy>(
      `${this.base}/platform/campaigns/policies/${id}/enable`,
      {}
    );
  }

  disablePlatformCampaignPolicy(id: number): Observable<PlatformCampaignPolicy> {
    return this.http.post<PlatformCampaignPolicy>(
      `${this.base}/platform/campaigns/policies/${id}/disable`,
      {}
    );
  }

  deletePlatformCampaignPolicy(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/platform/campaigns/policies/${id}`);
  }

  campaignNotices(): Observable<CampaignNotice[]> {
    return this.http.get<CampaignNotice[]>(`${this.base}/campaign-notices`);
  }

  readCampaignNotice(grantId: number): Observable<void> {
    return this.http.post<void>(`${this.base}/campaign-notices/${grantId}/read`, {});
  }

  // Invitaciones (T-004 etapa 3)
  platformInvitations(): Observable<PlatformInvitation[]> {
    return this.http.get<PlatformInvitation[]>(`${this.base}/platform/invitations`);
  }

  createPlatformInvitation(draft: PlatformInvitationDraft): Observable<PlatformInvitation> {
    return this.http.post<PlatformInvitation>(`${this.base}/platform/invitations`, draft);
  }

  regeneratePlatformInvitation(id: number): Observable<PlatformInvitation> {
    return this.http.post<PlatformInvitation>(
      `${this.base}/platform/invitations/${id}/regenerate-token`,
      {}
    );
  }

  cancelPlatformInvitation(id: number): Observable<PlatformInvitation> {
    return this.http.post<PlatformInvitation>(
      `${this.base}/platform/invitations/${id}/cancel`,
      {}
    );
  }

  invitationPreview(token: string): Observable<InvitationPreview> {
    return this.http.get<InvitationPreview>(
      `${this.base}/invitations/${encodeURIComponent(token)}`
    );
  }

  redeemInvitation(token: string): Observable<InvitationRedemption> {
    return this.http.post<InvitationRedemption>(
      `${this.base}/invitations/${encodeURIComponent(token)}/redeem`,
      {}
    );
  }
}
