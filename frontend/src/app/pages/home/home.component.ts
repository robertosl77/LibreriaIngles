import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ClassSummary } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { ExamCardComponent } from '../../shared/exam-card.component';
import { MyServiceComponent } from '../../shared/my-service.component';
import { STATUS_LABELS, statusChip } from '../../shared/status';

@Component({
  selector: 'app-home',
  imports: [RouterLink, DatePipe, ExamCardComponent, MyServiceComponent],
  styles: `
    .new-class { display: flex; flex-direction: column; align-items: flex-end; gap: 0.35rem; }
    .setup h2 { margin-bottom: 0.8rem; }
    .steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.2rem; }
    .steps li { display: flex; align-items: center; gap: 0.9rem; padding: 0.7rem 0; border-top: 1px solid var(--border); }
    .steps li:first-child { border-top: 0; }
    .steps li > div { flex: 1; }
    .steps p { margin: 0.15rem 0 0; }
    .check {
      width: 1.8rem; height: 1.8rem; border-radius: 50%;
      display: inline-flex; align-items: center; justify-content: center;
      border: 1px solid var(--border); font-weight: 700; font-size: 0.85rem; flex: none;
    }
    .steps li.done .check { background: var(--ok-bg); color: var(--ok); border-color: transparent; }
    .steps li.done strong { color: var(--muted); }
    @media (max-width: 640px) { .new-class { align-items: flex-start; } }
    .chip-exam { margin-left: 0.4rem; background: #fbf3dc; color: #8a6a1f; }
  `,
  template: `
    <main class="page stack">
      <div class="page-header">
        <div>
          <p class="muted small">Hola{{ name() ? ', ' + name() : '' }}</p>
          <h1>Tu práctica de hoy</h1>
        </div>
        <div class="new-class">
          <button
            class="btn btn-primary"
            type="button"
            (click)="newClass()"
            [disabled]="creating() || !canCreate()"
          >
            @if (creating()) {
              <span class="spinner"></span> Generando clase…
            } @else {
              Nueva clase
            }
          </button>
          @if (!canCreate()) {
            <span class="muted small">Completá los primeros pasos para empezar.</span>
          }
        </div>
      </div>

      @if (!setupDone()) {
        <section class="card setup">
          <h2>Primeros pasos</h2>
          <ol class="steps">
            <li [class.done]="hasLevel()">
              <span class="check" aria-hidden="true">{{ hasLevel() ? '✓' : '1' }}</span>
              <div>
                <strong>Elegí tu nivel</strong>
                @if (hasLevel()) {
                  <span class="muted small"> · {{ auth.me()?.studyProfile?.operationalLevel }}</span>
                } @else {
                  <p class="muted small">Define la dificultad de tus clases. Podés cambiarlo cuando quieras.</p>
                }
              </div>
              @if (!hasLevel()) { <a class="btn btn-sm btn-primary" routerLink="/app/nivel">Elegir nivel</a> }
            </li>
            <li [class.done]="hasAi()">
              <span class="check" aria-hidden="true">{{ hasAi() ? '✓' : '2' }}</span>
              <div>
                <strong>Conectá una IA</strong>
                @switch (ownKeys()) {
                  @case ('unused') {
                    <p class="muted small">Tu servicio usa la IA de Librería Inglés: no tenés que configurar nada.</p>
                  }
                  @case ('optional') {
                    <p class="muted small">
                      Tu servicio usa la IA de Librería Inglés. Si cargás tus propias API keys, se usan primero.
                    </p>
                  }
                  @default {
                    @if (!hasAi()) {
                      <p class="muted small">Cargá tu API key de OpenAI, Gemini o Anthropic. Es la que genera y corrige tus clases.</p>
                    }
                  }
                }
              </div>
              @if (ownKeys() === 'optional') {
                <a class="btn btn-sm" routerLink="/app/ia">Agregar mis keys</a>
              } @else if (!hasAi()) {
                <a class="btn btn-sm" [class.btn-primary]="hasLevel()" routerLink="/app/ia">Configurar IA</a>
              }
            </li>
            <li>
              <span class="check" aria-hidden="true">3</span>
              <div>
                <strong>Hacé tu primera clase</strong>
                <p class="muted small">Con los dos pasos anteriores listos se habilita <strong>Nueva clase</strong>.</p>
              </div>
            </li>
          </ol>
        </section>
      } @else if ((auth.me()?.ai?.available ?? 0) === 0) {
        <div class="banner banner-bad">
          No hay conexiones de IA disponibles en este momento. Tu trabajo queda guardado y la
          corrección se reintenta sola. <a routerLink="/app/ia">Ver conexiones</a>
        </div>
      }

      <app-my-service [compact]="true" />

      @if (creating()) {
        <p class="banner banner-info small">
          La IA está armando una clase única para vos según tu nivel y tus puntos débiles. Puede
          tardar unos segundos.
        </p>
      }

      <section class="grid">
        <div class="card">
          <p class="muted small">Nivel operativo</p>
          <p class="big-number">{{ auth.me()?.studyProfile?.operationalLevel ?? '—' }}</p>
          <a class="small" routerLink="/app/nivel">{{ hasLevel() ? 'Cambiar nivel' : 'Elegir nivel' }}</a>
        </div>
        <div class="card">
          <p class="muted small">Progreso general</p>
          <p class="big-number">{{ overall() === null ? '—' : overall() + '%' }}</p>
          <a class="small" routerLink="/app/progreso">Ver dashboard</a>
        </div>
        <div class="card">
          <p class="muted small">Clases completadas</p>
          <p class="big-number">{{ auth.me()?.classes?.completed ?? 0 }}</p>
          <a class="small" routerLink="/app/historial">Ver historial</a>
        </div>
        <div class="card">
          <p class="muted small">IA</p>
          <p class="big-number">{{ auth.me()?.ai?.available ?? 0 }}/{{ auth.me()?.ai?.connections ?? 0 }}</p>
          <a class="small" routerLink="/app/ia">Conexiones disponibles</a>
        </div>
      </section>

      @if (setupDone() && !loading()) {
        <app-exam-card />
      }

      @if (pending().length) {
        <section class="card">
          <h2>Pendientes</h2>
          <ul class="list">
            @for (item of pending(); track item.id) {
              <li class="list-item">
                <div>
                  <a [routerLink]="['/app/clase', item.id]"><strong>{{ item.title || 'Clase ' + item.id }}</strong></a>
                  @if (item.kind === 'EXAM') { <span class="chip chip-exam">Examen</span> }
                  <div class="muted small">
                    {{ item.targetLevel }} · {{ item.createdAt | date: 'dd/MM HH:mm' }}
                    @if (item.status === 'IN_PROGRESS' && item.total) {
                      · {{ item.answered }}/{{ item.total }} respondidos
                    }
                  </div>
                </div>
                <span [class]="statusChip(item.status)">{{ labels[item.status] }}</span>
              </li>
            }
          </ul>
        </section>
      }

      <section class="card">
        <h2>Últimas clases</h2>
        @if (loading()) {
          <p class="muted"><span class="spinner"></span></p>
        } @else if (recent().length === 0) {
          <p class="muted">
            Todavía no hiciste ninguna clase.
            @if (canCreate()) { Tocá <strong>Nueva clase</strong> para empezar. }
          </p>
        } @else {
          <ul class="list">
            @for (item of recent(); track item.id) {
              <li class="list-item">
                <div>
                  <a [routerLink]="['/app/clase', item.id]"><strong>{{ item.title || 'Clase ' + item.id }}</strong></a>
                  @if (item.kind === 'EXAM') { <span class="chip chip-exam">Examen</span> }
                  <div class="muted small">{{ item.targetLevel }} · {{ item.createdAt | date: 'dd/MM HH:mm' }}</div>
                </div>
                <strong>{{ item.score === null ? '' : item.score + '%' }}</strong>
              </li>
            }
          </ul>
        }
      </section>
    </main>
  `
})
export class HomeComponent implements OnInit {
  readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  readonly labels = STATUS_LABELS;
  readonly statusChip = statusChip;
  readonly classes = signal<ClassSummary[]>([]);
  readonly loading = signal(true);
  readonly creating = signal(false);
  readonly overall = signal<number | null>(null);
  readonly hasLevel = computed(() => !!this.auth.me()?.studyProfile.operationalLevel);
  readonly ownKeys = computed(() => this.auth.me()?.service.ownKeys ?? 'required');
  /** Paso 2 listo: el servicio no exige keys propias, o ya cargó alguna. */
  readonly hasAi = computed(
    () => this.ownKeys() !== 'required' || (this.auth.me()?.ai.own ?? 0) > 0
  );
  readonly setupDone = computed(() => this.hasLevel() && this.hasAi());
  readonly canCreate = computed(() => this.setupDone());
  readonly name = computed(() => this.auth.me()?.account.displayName?.split(' ')[0] ?? '');
  readonly pending = computed(() => this.classes().filter((c) => c.status !== 'COMPLETED'));
  readonly recent = computed(() => this.classes().filter((c) => c.status === 'COMPLETED').slice(0, 5));

  async ngOnInit(): Promise<void> {
    try {
      const me = await this.auth.refreshMe();
      // Documento funcional §27.2: al volver a entrar, reintentar correcciones pendientes.
      if (me.classes.awaitingEvaluation > 0 && me.ai.available > 0) {
        const result = await firstValueFrom(this.api.processPending());
        if (result.completed > 0) {
          this.toast.success(`Se corrigieron ${result.completed} clase(s) pendiente(s).`);
          await this.auth.refreshMe();
        }
      }
      const [classes, progress] = await Promise.all([
        firstValueFrom(this.api.classes()),
        firstValueFrom(this.api.progress())
      ]);
      this.classes.set(classes);
      this.overall.set(progress.overallScore);
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  async newClass(): Promise<void> {
    this.creating.set(true);
    try {
      const created = await firstValueFrom(this.api.createClass());
      if (created.notice) {
        this.toast.show(created.notice);
      }
      await this.router.navigate(['/app/clase', created.id]);
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo generar la clase.'));
    } finally {
      this.creating.set(false);
    }
  }
}
