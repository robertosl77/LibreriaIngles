import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  AiConnection,
  AuthConfig,
  Certificate,
  ClassDetail,
  ClassSummary,
  ConnectionDraft,
  ConnectionScope,
  Dashboard,
  ExamStatus,
  LessonResponse,
  Me,
  ModelOption,
  PlatformOverview,
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

  // Auth
  authConfig(): Observable<AuthConfig> {
    return this.http.get<AuthConfig>(`${this.base}/auth/config`);
  }

  loginGoogle(credential: string): Observable<TokenResponse> {
    return this.http.post<TokenResponse>(`${this.base}/auth/google`, { credential });
  }

  loginDev(email: string, name: string | null): Observable<TokenResponse> {
    return this.http.post<TokenResponse>(`${this.base}/auth/dev-login`, { email, name });
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

  getClass(id: number): Observable<ClassDetail> {
    return this.http.get<ClassDetail>(`${this.base}/classes/${id}`);
  }

  saveAnswer(classId: number, exerciseId: number, answer: string): Observable<{ savedAt: string }> {
    return this.http.put<{ savedAt: string }>(
      `${this.base}/classes/${classId}/answers/${exerciseId}`,
      { answer }
    );
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

  /** "Necesito lección" (T-020): devuelve la lección y registra la ayuda si la clase está abierta. */
  lesson(classId: number, exerciseId: number): Observable<LessonResponse> {
    return this.http.post<LessonResponse>(
      `${this.base}/classes/${classId}/exercises/${exerciseId}/lesson`,
      {}
    );
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
}
