import { DatePipe } from '@angular/common';
import { Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AuthService } from '../core/auth.service';
import { AiSource } from '../core/models';

export const SOURCE_LABELS: Record<AiSource, string> = {
  BYOK: 'Tus propias API keys',
  PLATFORM: 'IA de Librería Inglés',
  HYBRID: 'Híbrido: tus keys y, si fallan, Librería Inglés'
};

const DAY_MS = 24 * 60 * 60 * 1000;

/** "Tu servicio" (T-004): qué IA usás, hasta cuándo y cuánto te queda de hoy. */
@Component({
  selector: 'app-my-service',
  imports: [DatePipe, RouterLink],
  template: `
    @if (service(); as s) {
      @if (s.expired) {
        <div class="banner small" role="status">
          Tu servicio <strong>{{ s.expired.name }}</strong> venció el
          {{ s.expired.at | date: 'dd/MM/yyyy' }}. Volviste a usar tus propias API keys.
          @if (ownKeys() === 0) {
            <a routerLink="/app/ia">Cargá una API key</a> para seguir generando clases.
          }
        </div>
      }
      @if (!compact() || s.granted) {
        <section class="card service">
          <div class="head">
            <div>
              <p class="muted small">Tu servicio</p>
              <h2>{{ s.name }}</h2>
            </div>
            <span class="chip" [class.chip-ok]="s.usesPlatform">{{ sourceLabel() }}</span>
          </div>
          <p class="small muted detail">
            @if (s.granted) {
              @if (s.expiresAt) {
                Vence el <strong>{{ s.expiresAt | date: 'dd/MM/yyyy HH:mm' }}</strong>
                ({{ daysLeftLabel() }}).
              } @else {
                Sin vencimiento.
              }
            } @else {
              Generás y corregís tus clases con tus propias API keys.
            }
            @if (s.source === 'PLATFORM' && ownKeys() > 0) {
              Tus conexiones propias quedan guardadas pero no se usan mientras tengas este servicio;
              cuando venza, vuelven a usarse.
            }
            @if (s.source === 'HYBRID') {
              Primero se usan tus conexiones; si fallan, la IA de Librería Inglés.
            }
          </p>
          @if (usedPercent() !== null) {
            <div class="usage">
              <div class="bar" role="progressbar" [attr.aria-valuenow]="usedPercent()" aria-valuemin="0" aria-valuemax="100">
                <span [style.width.%]="usedPercent()"></span>
              </div>
              <span class="small muted">Uso de hoy: {{ usedPercent() }}%</span>
            </div>
          }
        </section>
      }
    }
  `,
  styles: `
    .service { display: flex; flex-direction: column; gap: 0.5rem; }
    .head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
    .head h2 { margin: 0.1rem 0 0; }
    .head p { margin: 0; }
    .detail { margin: 0; }
    .usage { display: flex; align-items: center; gap: 0.8rem; }
    .usage .bar { flex: 1; max-width: 18rem; }
  `
})
export class MyServiceComponent {
  private readonly auth = inject(AuthService);

  /** En el inicio solo se muestra si hay un servicio otorgado o un aviso. */
  readonly compact = input(false);

  readonly service = computed(() => this.auth.me()?.service ?? null);
  readonly ownKeys = computed(() => this.auth.me()?.ai.own ?? 0);
  readonly sourceLabel = computed(() => {
    const s = this.service();
    return s ? SOURCE_LABELS[s.source] : '';
  });
  readonly usedPercent = computed(() => {
    const s = this.service();
    if (!s?.dailyRequestLimit || s.platformRequests24h === undefined) {
      return null;
    }
    return Math.min(100, Math.round((s.platformRequests24h / s.dailyRequestLimit) * 100));
  });
  readonly daysLeftLabel = computed(() => {
    const expires = this.service()?.expiresAt;
    if (!expires) {
      return '';
    }
    const days = Math.ceil((new Date(expires).getTime() - Date.now()) / DAY_MS);
    if (days <= 1) {
      return 'último día';
    }
    return `quedan ${days} días`;
  });
}
