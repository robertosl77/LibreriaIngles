import { AfterViewInit, Component, ElementRef, NgZone, OnInit, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { AuthConfig } from '../../core/models';

interface GoogleAccounts {
  accounts: {
    id: {
      initialize(options: { client_id: string; callback: (response: { credential: string }) => void }): void;
      renderButton(element: HTMLElement, options: Record<string, unknown>): void;
    };
  };
}

declare global {
  interface Window {
    google?: GoogleAccounts;
  }
}

const GIS_SRC = 'https://accounts.google.com/gsi/client';

function loadGoogleScript(): Promise<void> {
  if (window.google?.accounts) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${GIS_SRC}"]`);
    const script = existing ?? document.createElement('script');
    script.addEventListener('load', () => resolve());
    script.addEventListener('error', () => reject(new Error('No se pudo cargar Google')));
    if (!existing) {
      script.src = GIS_SRC;
      script.async = true;
      document.head.appendChild(script);
    }
  });
}

@Component({
  selector: 'app-login',
  imports: [FormsModule, RouterLink],
  template: `
    <main class="login">
      <a class="brand" routerLink="/">Librería Inglés</a>
      <section class="card login-card stack">
        <div>
          <h1>Ingresar</h1>
          <p class="muted">Tu cuenta personal se crea automáticamente la primera vez.</p>
          @if (inviteToken) {
            <p class="banner small">Ingresá con la cuenta que debe recibir la invitación.</p>
          }
        </div>

        @if (loading()) {
          <p class="muted"><span class="spinner"></span> Cargando…</p>
        } @else {
          @if (config()?.googleClientId) {
            <div #googleButton class="google-button"></div>
          } @else {
            <p class="banner small">
              El login con Google no está configurado: falta <code>GOOGLE_CLIENT_ID</code> en el
              <code>.env</code> del backend.
            </p>
          }

          @if (config()?.devLoginEnabled) {
            <form class="stack dev" (ngSubmit)="devLogin()">
              <p class="small muted">
                <strong>Modo desarrollo:</strong> ingreso sin Google (solo en local).
              </p>
              <label class="field">
                Email
                <input class="input" type="email" name="email" [(ngModel)]="email" required autocomplete="email" />
              </label>
              <label class="field">
                Nombre (opcional)
                <input class="input" type="text" name="name" [(ngModel)]="name" autocomplete="name" />
              </label>
              <button class="btn" type="submit" [disabled]="busy() || !email">Ingresar en modo desarrollo</button>
            </form>
          }
        }

        @if (error()) {
          <p class="banner banner-bad small">{{ error() }}</p>
        }
      </section>
    </main>
  `,
  styles: `
    .login {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2rem 1rem;
      gap: 2rem;
    }
    .brand {
      font-weight: 750;
      font-size: 1.15rem;
      text-decoration: none;
      align-self: flex-start;
      max-width: 440px;
      width: 100%;
      margin: 0 auto;
    }
    .login-card {
      width: 100%;
      max-width: 440px;
    }
    h1 { margin: 0 0 0.3rem; }
    .google-button { min-height: 44px; }
    .dev {
      border-top: 1px solid var(--border);
      padding-top: 1rem;
    }
  `
})
export class LoginComponent implements OnInit, AfterViewInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly zone = inject(NgZone);
  private readonly route = inject(ActivatedRoute);

  readonly googleButton = viewChild<ElementRef<HTMLDivElement>>('googleButton');
  readonly config = signal<AuthConfig | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  email = '';
  name = '';
  inviteToken: string | null = null;

  async ngOnInit(): Promise<void> {
    this.inviteToken = this.route.snapshot.queryParamMap.get('invite');
    try {
      this.config.set(await firstValueFrom(this.api.authConfig()));
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo obtener la configuración de login.'));
    } finally {
      this.loading.set(false);
      setTimeout(() => this.renderGoogle());
    }
  }

  ngAfterViewInit(): void {
    this.renderGoogle();
  }

  private async renderGoogle(): Promise<void> {
    const clientId = this.config()?.googleClientId;
    const element = this.googleButton()?.nativeElement;
    if (!clientId || !element || element.childElementCount > 0) {
      return;
    }
    try {
      await loadGoogleScript();
      window.google!.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => this.zone.run(() => this.googleLogin(response.credential))
      });
      window.google!.accounts.id.renderButton(element, {
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        locale: 'es'
      });
    } catch {
      this.error.set('No se pudo cargar el botón de Google.');
    }
  }

  private async googleLogin(credential: string): Promise<void> {
    await this.run(() => firstValueFrom(this.api.loginGoogle(credential, this.inviteToken)));
  }

  async devLogin(): Promise<void> {
    await this.run(() =>
      firstValueFrom(this.api.loginDev(this.email.trim(), this.name.trim() || null, this.inviteToken))
    );
  }

  private async run(request: () => Promise<{ accessToken: string }>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const token = await request();
      const redirect = this.inviteToken
        ? `/invitacion/${encodeURIComponent(this.inviteToken)}`
        : null;
      await this.auth.completeLogin(token.accessToken, redirect);
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo iniciar sesión.'));
    } finally {
      this.busy.set(false);
    }
  }
}
