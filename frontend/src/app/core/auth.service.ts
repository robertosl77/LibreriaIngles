import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';
import { Me } from './models';

const TOKEN_KEY = 'li_token';

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
    const me = await firstValueFrom(this.api.me());
    this.me.set(me);
    return me;
  }

  logout(redirect = true): void {
    this.setToken(null);
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
