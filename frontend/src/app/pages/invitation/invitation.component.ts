import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { InvitationPreview, InvitationRedemption } from '../../core/models';

@Component({
  selector: 'app-invitation',
  imports: [DatePipe, RouterLink],
  template: `
    <main class="invite-page">
      <a class="brand" routerLink="/">Librería Inglés</a>
      <section class="card invite-card stack">
        @if (loading()) {
          <p class="muted"><span class="spinner"></span> Cargando invitación…</p>
        } @else if (preview(); as invitation) {
          <div>
            <h1>{{ invitation.name }}</h1>
            <p class="muted">
              Beneficio: <strong>{{ invitation.benefitName }}</strong> · {{ invitation.serviceName }}
              @if (invitation.durationDays) { · {{ invitation.durationDays }} días }
            </p>
          </div>

          @if (invitation.recipientMode === 'NAMED' && invitation.recipientEmailHint) {
            <p class="banner small">
              Invitación nominada para {{ invitation.recipientEmailHint }}. Ingresá con esa identidad.
            </p>
          } @else if (invitation.recipientMode === 'OPEN') {
            <p class="banner small">
              Link abierto · {{ invitation.remaining }} canje(s) disponible(s).
            </p>
          }

          @if (invitation.expiresAt) {
            <p class="muted small">El link vence {{ invitation.expiresAt | date: 'dd/MM/yyyy HH:mm' }}.</p>
          }

          @if (result(); as redeemed) {
            <p class="banner banner-good">
              {{ redeemed.alreadyRedeemed ? 'Esta invitación ya estaba canjeada por tu cuenta.' : 'Invitación canjeada.' }}
              <strong>{{ redeemed.benefit }}</strong>
            </p>
            <button class="btn btn-primary" type="button" (click)="continue()">Continuar</button>
          } @else if (claimError()) {
            <p class="banner banner-bad">{{ claimError() }}</p>
            @if (auth.isLoggedIn()) {
              <button class="btn" type="button" (click)="continue()">Continuar sin este beneficio</button>
            }
          } @else if (!auth.isLoggedIn()) {
            @if (invitation.status === 'ACTIVE') {
              <button class="btn btn-primary" type="button" (click)="login()">Ingresar con Google para aceptar</button>
            } @else {
              <p class="banner banner-bad">Esta invitación ya no está disponible ({{ invitation.status }}).</p>
              <a class="btn" routerLink="/login">Ingresar normalmente</a>
            }
          } @else if (redeeming()) {
            <p class="muted"><span class="spinner"></span> Aplicando beneficio…</p>
          }
        } @else {
          <p class="banner banner-bad">{{ loadError() || 'No se pudo cargar la invitación.' }}</p>
          <a class="btn" routerLink="/login">Ingresar normalmente</a>
        }
      </section>
    </main>
  `,
  styles: `
    .invite-page {
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
      max-width: 520px;
      width: 100%;
      margin: 0 auto;
    }
    .invite-card { width: 100%; max-width: 520px; }
    h1 { margin: 0 0 0.4rem; }
  `
})
export class InvitationComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly auth = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly preview = signal<InvitationPreview | null>(null);
  readonly result = signal<InvitationRedemption | null>(null);
  readonly loading = signal(true);
  readonly redeeming = signal(false);
  readonly loadError = signal<string | null>(null);
  readonly claimError = signal<string | null>(null);

  private token = '';

  async ngOnInit(): Promise<void> {
    this.token = this.route.snapshot.paramMap.get('token') ?? '';
    try {
      this.preview.set(await firstValueFrom(this.api.invitationPreview(this.token)));
    } catch (err) {
      this.loadError.set(errorMessage(err, 'La invitación no existe.'));
    } finally {
      this.loading.set(false);
    }
    if (this.auth.isLoggedIn() && this.preview()) {
      await this.redeem();
    }
  }

  login(): void {
    void this.router.navigate(['/login'], { queryParams: { invite: this.token } });
  }

  async redeem(): Promise<void> {
    this.redeeming.set(true);
    this.claimError.set(null);
    try {
      this.result.set(await firstValueFrom(this.api.redeemInvitation(this.token)));
      await this.auth.refreshMe();
    } catch (err) {
      this.claimError.set(errorMessage(err, 'La invitación no pudo aplicarse.'));
    } finally {
      this.redeeming.set(false);
    }
  }

  continue(): void {
    const me = this.auth.me();
    void this.router.navigate(me?.studyProfile.operationalLevel ? ['/app'] : ['/app/nivel']);
  }
}
