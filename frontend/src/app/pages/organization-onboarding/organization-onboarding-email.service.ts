import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export interface EmailVerificationStartResult {
  challengeId: string;
  email: string;
  expiresAt: string;
  resendAvailableInSeconds: number;
  deliveryProvider: string;
  developmentCode: string | null;
}

export interface EmailVerificationResult {
  verified: boolean;
  status: string;
  verifiedAt: string | null;
}

@Injectable({ providedIn: 'root' })
export class OrganizationOnboardingEmailService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/organization-onboarding`;

  private headers(token: string): HttpHeaders {
    return new HttpHeaders({ 'X-Onboarding-Token': token });
  }

  start(publicId: string, token: string): Observable<EmailVerificationStartResult> {
    return this.http.post<EmailVerificationStartResult>(
      `${this.base}/${publicId}/email-verification/start`,
      {},
      { headers: this.headers(token) }
    );
  }

  resend(publicId: string, token: string): Observable<EmailVerificationStartResult> {
    return this.http.post<EmailVerificationStartResult>(
      `${this.base}/${publicId}/email-verification/resend`,
      {},
      { headers: this.headers(token) }
    );
  }

  verify(publicId: string, token: string, code: string): Observable<EmailVerificationResult> {
    return this.http.post<EmailVerificationResult>(
      `${this.base}/${publicId}/email-verification/verify`,
      { code },
      { headers: this.headers(token) }
    );
  }

  changeEmail(
    publicId: string,
    token: string,
    email: string
  ): Observable<{ email: string; emailVerified: boolean; status: string }> {
    return this.http.patch<{ email: string; emailVerified: boolean; status: string }>(
      `${this.base}/${publicId}/referent-email`,
      { email },
      { headers: this.headers(token) }
    );
  }
}
