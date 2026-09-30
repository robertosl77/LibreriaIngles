import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ToastService } from '../../core/toast.service';

const DESCRIPTIONS: Record<string, string> = {
  A1: 'Principiante: frases cotidianas y presentaciones.',
  A2: 'Básico: situaciones simples y rutinarias.',
  B1: 'Intermedio: temas conocidos, trabajo y viajes.',
  B2: 'Intermedio alto: textos complejos y conversación fluida.',
  C1: 'Avanzado: uso flexible y eficaz del idioma.',
  C2: 'Maestría: comprensión y expresión casi nativas.'
};

@Component({
  selector: 'app-level',
  template: `
    <main class="page">
      <div class="page-header">
        <div>
          <h1>¿En qué nivel querés empezar?</h1>
          <p class="muted">
            Podés elegir cualquier nivel disponible. Con la práctica, el sistema va a ajustar tu
            nivel operativo según la evidencia.
          </p>
        </div>
      </div>

      <div class="grid">
        @for (level of levels(); track level) {
          <button
            type="button"
            class="card level"
            [class.selected]="level === current()"
            [disabled]="!available().includes(level) || busy()"
            (click)="choose(level)"
          >
            <span class="big-number">{{ level }}</span>
            <span class="muted small">{{ descriptions[level] }}</span>
            @if (!available().includes(level)) {
              <span class="chip">Próximamente</span>
            } @else if (level === current()) {
              <span class="chip chip-ok">Nivel actual</span>
            }
          </button>
        }
      </div>

      <p class="muted small diag">
        El diagnóstico adaptativo llega en una próxima etapa. Por ahora la currícula disponible es A1.
      </p>
    </main>
  `,
  styles: `
    .level {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      gap: 0.6rem;
      text-align: left;
      font: inherit;
      cursor: pointer;
      min-height: 150px;
    }
    .level:disabled { cursor: not-allowed; opacity: 0.55; }
    .level:not(:disabled):hover { border-color: #111; }
    .level.selected { border-color: #111; box-shadow: 0 0 0 1px #111 inset; }
    .diag { margin-top: 1.5rem; }
  `
})
export class LevelComponent {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  readonly descriptions = DESCRIPTIONS;
  readonly levels = signal<string[]>(this.auth.me()?.levels.all ?? ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']);
  readonly available = signal<string[]>(this.auth.me()?.levels.available ?? ['A1']);
  readonly current = signal<string | null>(this.auth.me()?.studyProfile.operationalLevel ?? null);
  readonly busy = signal(false);

  async choose(level: string): Promise<void> {
    this.busy.set(true);
    try {
      const me = await firstValueFrom(this.api.setLevel(level));
      this.auth.me.set(me);
      this.toast.success(`Nivel ${level} seleccionado.`);
      await this.router.navigate(['/app']);
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busy.set(false);
    }
  }
}
