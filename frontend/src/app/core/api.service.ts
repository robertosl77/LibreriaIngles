import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  AiConnection,
  AuthConfig,
  ClassDetail,
  ClassSummary,
  ConnectionScope,
  Dashboard,
  Me,
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

  createConnection(body: {
    provider: string;
    name: string;
    model: string | null;
    apiKey: string | null;
    priority: number;
    scope: ConnectionScope;
  }): Observable<AiConnection> {
    return this.http.post<AiConnection>(`${this.base}/ai/connections`, body);
  }

  updateConnection(
    id: number,
    body: Partial<{ name: string; model: string; apiKey: string; priority: number; active: boolean }>
  ): Observable<AiConnection> {
    return this.http.patch<AiConnection>(`${this.base}/ai/connections/${id}`, body);
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
}
