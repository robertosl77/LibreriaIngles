import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';
import { Me } from './models';

const TOKEN_KEY = 'li_token';
/** T-220 (E-01): empresa elegida; el interceptor la manda como X-Organization-Id. */
const ORGANIZATION_KEY = 'li_organization';

function readOrganization(): number | null {
  try {
    const raw = localStorage.getItem(ORGANIZATION_KEY);
    return raw ? Number(raw) || null : null;
  } catch {
    return null;
  }
}

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly token = signal<string | null>(readToken());
  readonly organizationId = signal<number | null>(readOrganization());
  readonly me = signal<Me | null>(null);
  readonly isLoggedIn = computed(() => this.token() !== null);

  async completeLogin(accessToken: string, redirectTo: string | null = null): Promise<void> {
    this.setToken(accessToken);
    await this.refreshMe();
    if (redirectTo) {
      await this.router.navigateByUrl(redirectTo);
      return;
    }
    const me = this.me();
    await this.router.navigate(me?.studyProfile.operationalLevel ? ['/app'] : ['/app/nivel']);
  }

  async refreshMe(): Promise<Me> {
    let me: Me;
    try {
      me = await firstValueFrom(this.api.me());
    } catch (err) {
      // La empresa guardada ya no es válida (membresía revocada): se vuelve a personal.
      if (err instanceof HttpErrorResponse && err.status === 403 && this.organizationId() !== null) {
        this.setOrganization(null);
        me = await firstValueFrom(this.api.me());
      } else {
        throw err;
      }
    }
    this.me.set(me);
    return me;
  }

  /** Cambia la empresa en la que actúa la sesión (null = personal) y recarga los datos. */
  async switchOrganization(organizationId: number | null): Promise<void> {
    this.setOrganization(organizationId);
    await this.refreshMe();
    await this.router.navigate(['/app']);
  }

  private setOrganization(value: number | null): void {
    this.organizationId.set(value);
    try {
      if (value) {
        localStorage.setItem(ORGANIZATION_KEY, String(value));
      } else {
        localStorage.removeItem(ORGANIZATION_KEY);
      }
    } catch {
      // Sin storage: la elección dura lo que dure la pestaña.
    }
  }

  logout(redirect = true): void {
    this.setToken(null);
    this.setOrganization(null);
    this.me.set(null);
    if (redirect) {
      void this.router.navigate(['/login']);
    }
  }

  private setToken(value: string | null): void {
    this.token.set(value);
    try {
      if (value) {
        localStorage.setItem(TOKEN_KEY, value);
      } else {
        localStorage.removeItem(TOKEN_KEY);
      }
    } catch {
      // Sin storage disponible la sesión dura lo que dure la pestaña.
    }
  }
}
