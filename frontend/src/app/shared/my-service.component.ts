import { DatePipe } from '@angular/common';
import { Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AuthService } from '../core/auth.service';
import { AiSource } from '../core/models';
import { BrandService } from '../core/brand.service';

/** T-220 (E-13): la marca llega del backend; las etiquetas se arman con ella. */
export function sourceLabel(source: AiSource, brand: string): string {
  switch (source) {
    case 'BYOK':
      return 'Tus propias API keys';
    case 'PLATFORM':
      return `IA de ${brand}`;
    case 'HYBRID':
      return `Híbrido: tus keys y, si fallan, ${brand}`;
  }
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** "Tu servicio" (T-004): qué IA usás y hasta cuándo. Los límites viven en las conexiones. */
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
            @if (s.source === 'HYBRID') {
              Primero se usan tus conexiones; si fallan, la IA de {{ brand.name() }}.
            }
          </p>
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
  `
})
export class MyServiceComponent {
  readonly brand = inject(BrandService);
  private readonly auth = inject(AuthService);

  /** En el inicio solo se muestra si hay un servicio otorgado o un aviso. */
  readonly compact = input(false);

  readonly service = computed(() => this.auth.me()?.service ?? null);
  readonly ownKeys = computed(() => this.auth.me()?.ai.own ?? 0);
  readonly sourceLabel = computed(() => {
    const s = this.service();
    return s ? sourceLabel(s.source, this.brand.name()) : '';
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
