import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export interface WebsiteCheckResult {
  state: 'VERIFIED' | 'UNREACHABLE' | 'INVALID';
  normalizedUrl: string | null;
  message: string;
  statusCode: number | null;
}

export interface PhoneNormalizeResult {
  e164: string;
  display: string;
  phoneType: 'MOBILE' | 'FIXED_LINE' | 'FIXED_OR_MOBILE' | 'OTHER';
}

@Injectable({ providedIn: 'root' })
export class OrganizationOnboardingValidationService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiUrl;

  checkWebsite(website: string): Observable<WebsiteCheckResult> {
    return this.http.post<WebsiteCheckResult>(
      `${this.base}/organization-onboarding/website/check`,
      { website }
    );
  }

  normalizePhone(country: string, phone: string): Observable<PhoneNormalizeResult> {
    return this.http.post<PhoneNormalizeResult>(
      `${this.base}/organization-onboarding/phone/normalize`,
      { country, phone }
    );
  }
}
