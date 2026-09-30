import { DatePipe, NgTemplateOutlet } from '@angular/common';
import { Component, OnDestroy, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
  Observable,
  Subject,
  Subscription,
  catchError,
  debounce,
  firstValueFrom,
  groupBy,
  map,
  mergeMap,
  of,
  switchMap,
  timer
} from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ClassDetail, Exercise } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { STATUS_LABELS, scoreChip, statusChip } from '../../shared/status';

type SaveState = 'saving' | 'saved' | 'error';

const TYPE_LABELS: Record<Exercise['type'], string> = {
  fill_blank: 'Completar',
  multiple_choice: 'Opción múltiple',
  reading_multiple_choice: 'Lectura',
  rewrite: 'Reescribir',
  short_writing: 'Escritura'
};

const RESULT_LABELS: Record<string, string> = {
  correct: 'Correcto',
  partially_correct: 'Parcial',
  incorrect: 'Incorrecto'
};

@Component({
  selector: 'app-class',
  imports: [FormsModule, RouterLink, DatePipe, NgTemplateOutlet],
  template: `
    <main class="page stack">
      @if (loading()) {
        <p class="muted"><span class="spinner"></span> Cargando clase…</p>
      }
      @if (!loading() && klass(); as c) {
        <div class="page-header">
          <div>
            <p class="muted small">
              <a routerLink="/app">Inicio</a> · Clase #{{ c.id }} · {{ c.targetLevel }}
              @if (c.currentAttempt > 1) { · Intento {{ c.currentAttempt }} }
            </p>
            <h1>{{ c.title || 'Clase ' + c.id }}</h1>
          </div>
          <span [class]="statusChip(c.status)">{{ labels[c.status] }}</span>
        </div>

        @if (c.status === 'GENERATION_FAILED') {
          <div class="card stack">
            <p class="banner banner-bad">No se pudo generar la clase. {{ c.generationError }}</p>
            <p class="muted small">La solicitud quedó guardada: podés reintentar cuando haya una conexión de IA disponible.</p>
            <div class="row">
              <button class="btn btn-primary" type="button" (click)="retryGeneration()" [disabled]="busy()">
                @if (busy()) { <span class="spinner"></span> } Reintentar generación
              </button>
              <a class="btn" routerLink="/app/ia">Revisar conexiones</a>
            </div>
          </div>
        } @else if (c.status === 'GENERATING') {
          <p class="banner banner-info"><span class="spinner"></span> La clase se está generando…</p>
        } @else {
          @if (c.status === 'AWAITING_EVALUATION') {
            <div class="banner stack">
              <span>
                Tus respuestas están guardadas. La corrección está pendiente porque no hay
                conexiones de IA disponibles; se reintenta automáticamente cuando vuelvas a entrar.
              </span>
              <div class="row">
                <button class="btn btn-sm" type="button" (click)="retryEvaluation()" [disabled]="busy()">
                  @if (busy()) { <span class="spinner"></span> } Reintentar corrección ahora
                </button>
                <a class="btn btn-sm" routerLink="/app/ia">Revisar conexiones</a>
              </div>
            </div>
          }

          @if (c.status === 'COMPLETED') {
            <section class="card score-card">
              <div>
                <p class="muted small">Resultado</p>
                <p class="big-number">{{ c.score }}%</p>
              </div>
              @if (c.history.length > 1) {
                <div class="history">
                  @for (h of c.history; track h.attempt) {
                    <div class="small">
                      Intento {{ h.attempt }}: <strong>{{ h.score }}%</strong>
                    </div>
                  }
                </div>
              }
              <div class="row">
                <button class="btn" type="button" (click)="retake()" [disabled]="busy()">Rehacer esta clase</button>
                <a class="btn btn-primary" routerLink="/app">Volver al inicio</a>
              </div>
            </section>
          }

          @if (editable()) {
            <p class="muted small">
              Tus respuestas se guardan solas mientras escribís. {{ answeredCount() }}/{{ c.exercises.length }} respondidas.
            </p>
          }

          @for (exercise of c.exercises; track exercise.id; let i = $index) {
            <article class="card exercise" [class]="resultClass(exercise)">
              <header class="exercise-head">
                <span class="muted small">{{ i + 1 }}. {{ typeLabels[exercise.type] }} · {{ exercise.skillName }}</span>
                @if (editable() && saveState()[exercise.id]; as state) {
                  <span class="small muted">
                    @switch (state) {
                      @case ('saving') { Guardando… }
                      @case ('saved') { Guardado }
                      @case ('error') { <span class="error-text">No se pudo guardar</span> }
                    }
                  </span>
                }
                @if (exercise.result; as r) {
                  <span [class]="scoreChip(r.score)">{{ resultLabels[r.result || 'incorrect'] }} · {{ r.score }}%</span>
                }
              </header>

              @if (exercise.instruction) {
                <p class="instruction">{{ exercise.instruction }}</p>
              }
              @if (exercise.passage) {
                <blockquote class="passage">{{ exercise.passage }}</blockquote>
              }
              <p class="question">{{ exercise.question }}</p>

              @if (editable()) {
                @switch (exercise.type) {
                  @case ('multiple_choice') {
                    <ng-container *ngTemplateOutlet="options; context: { $implicit: exercise }" />
                  }
                  @case ('reading_multiple_choice') {
                    <ng-container *ngTemplateOutlet="options; context: { $implicit: exercise }" />
                  }
                  @case ('short_writing') {
                    <textarea
                      class="input"
                      rows="4"
                      [ngModel]="answers()[exercise.id]"
                      (ngModelChange)="onAnswer(exercise.id, $event)"
                      placeholder="Escribí tu respuesta en inglés…"
                    ></textarea>
                  }
                  @default {
                    <input
                      class="input"
                      type="text"
                      autocomplete="off"
                      autocapitalize="off"
                      spellcheck="false"
                      [ngModel]="answers()[exercise.id]"
                      (ngModelChange)="onAnswer(exercise.id, $event)"
                      [placeholder]="exercise.type === 'fill_blank' ? 'Palabra(s) que completan el espacio' : 'Escribí la oración completa'"
                    />
                  }
                }
              } @else {
                <p class="your-answer">
                  <span class="muted small">Tu respuesta:</span>
                  <strong>{{ exercise.answer || '(sin respuesta)' }}</strong>
                </p>
              }

              @if (exercise.result; as r) {
                <div class="feedback stack">
                  @if (r.feedback) { <p>{{ r.feedback }}</p> }
                  @if (r.correctAnswer && r.result !== 'correct') {
                    <p class="small"><span class="muted">Respuesta correcta: </span><strong>{{ r.correctAnswer }}</strong></p>
                  }
                  @for (err of r.errors; track $index) {
                    @if (err.explanation || err.correction) {
                      <p class="small error-line">
                        @if (err.fragment) { <s>{{ err.fragment }}</s> }
                        @if (err.correction) { → <strong>{{ err.correction }}</strong> }
                        @if (err.explanation) { <span class="muted"> · {{ err.explanation }}</span> }
                      </p>
                    }
                  }
                  @for (s of r.suggestions; track $index) {
                    <p class="small suggestion">💡 {{ s.text }}</p>
                  }
                  @if (r.appeal) {
                    <p class="small muted">
                      {{ r.appeal.accepted ? 'Revisión aceptada.' : 'Revisión: se mantuvo la corrección. ' + (r.appeal.feedback || '') }}
                    </p>
                  }
                  @if (r.canAppeal && c.status === 'COMPLETED') {
                    <button class="btn-link small" type="button" (click)="appeal(exercise.id)" [disabled]="busy()">
                      Creo que mi respuesta es correcta
                    </button>
                  }
                </div>
              }
            </article>
          }

          <ng-template #options let-exercise>
            <div class="options" role="radiogroup">
              @for (option of exercise.options; track option) {
                <label class="option" [class.checked]="answers()[exercise.id] === option">
                  <input
                    type="radio"
                    [name]="'ex-' + exercise.id"
                    [value]="option"
                    [checked]="answers()[exercise.id] === option"
                    (change)="onAnswer(exercise.id, option, true)"
                  />
                  {{ option }}
                </label>
              }
            </div>
          </ng-template>

          @if (editable()) {
            <div class="submit-bar">
              <span class="muted small">{{ answeredCount() }}/{{ c.exercises.length }} respondidas</span>
              <button class="btn btn-primary" type="button" (click)="submit()" [disabled]="busy()">
                @if (busy()) { <span class="spinner"></span> Corrigiendo… } @else { Finalizar y comprobar }
              </button>
            </div>
          }

          <p class="muted small">
            Creada {{ c.createdAt | date: 'dd/MM/yyyy HH:mm' }}
            @if (c.generatedBy) { · generada con {{ c.generatedBy }} }
          </p>
        }
      }
    </main>
  `,
  styles: `
    .exercise { display: flex; flex-direction: column; gap: 0.6rem; }
    .exercise.result-correct { border-left: 4px solid var(--ok); }
    .exercise.result-partial { border-left: 4px solid var(--warn); }
    .exercise.result-incorrect { border-left: 4px solid var(--bad); }
    .exercise-head { display: flex; gap: 0.6rem; align-items: center; justify-content: space-between; flex-wrap: wrap; }
    .instruction { margin: 0; font-weight: 600; }
    .question { margin: 0; font-size: 1.15rem; }
    .passage { margin: 0; padding: 0.8rem 1rem; background: var(--bg); border-radius: 0.6rem; line-height: 1.6; }
    .options { display: flex; flex-direction: column; gap: 0.4rem; }
    .option { display: flex; gap: 0.6rem; align-items: center; padding: 0.6rem 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; cursor: pointer; }
    .option.checked { border-color: #111; background: var(--bg); }
    .your-answer { margin: 0; display: flex; gap: 0.5rem; align-items: baseline; flex-wrap: wrap; }
    .feedback { gap: 0.4rem; border-top: 1px solid var(--border); padding-top: 0.6rem; }
    .feedback p { margin: 0; }
    .suggestion { color: #5a3d00; }
    .feedback .btn-link { align-self: flex-start; }
    .error-text { color: var(--bad); }
    .score-card { display: flex; gap: 1.5rem; align-items: center; justify-content: space-between; flex-wrap: wrap; }
    .score-card p { margin: 0; }
    .history { display: flex; flex-direction: column; gap: 0.2rem; }
    .submit-bar {
      position: sticky; bottom: 0.8rem;
      display: flex; align-items: center; justify-content: space-between; gap: 1rem;
      background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
      padding: 0.8rem 1rem; box-shadow: 0 6px 24px rgb(0 0 0 / 0.08);
    }
  `
})
export class ClassComponent implements OnDestroy {
  readonly id = input.required<string>();

  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);

  readonly labels = STATUS_LABELS;
  readonly typeLabels = TYPE_LABELS;
  readonly resultLabels = RESULT_LABELS;
  readonly statusChip = statusChip;
  readonly scoreChip = scoreChip;

  readonly klass = signal<ClassDetail | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly answers = signal<Record<number, string>>({});
  readonly saveState = signal<Record<number, SaveState>>({});

  readonly editable = computed(() => {
    const status = this.klass()?.status;
    return status === 'READY' || status === 'IN_PROGRESS';
  });
  readonly answeredCount = computed(
    () => Object.values(this.answers()).filter((a) => a && a.trim().length > 0).length
  );

  private readonly edits = new Subject<{ exerciseId: number; answer: string; immediate: boolean }>();
  private readonly subscription: Subscription;

  constructor() {
    // Autoguardado por ejercicio (documento funcional §20), con debounce independiente.
    this.subscription = this.edits
      .pipe(
        groupBy((edit) => edit.exerciseId),
        mergeMap((group) =>
          group.pipe(
            debounce((edit) => timer(edit.immediate ? 0 : 700)),
            switchMap((edit) =>
              this.api.saveAnswer(this.klass()!.id, edit.exerciseId, edit.answer).pipe(
                map(() => ({ exerciseId: edit.exerciseId, state: 'saved' as SaveState })),
                catchError(() => of({ exerciseId: edit.exerciseId, state: 'error' as SaveState }))
              )
            )
          )
        )
      )
      .subscribe(({ exerciseId, state }) => {
        if (this.editable()) {
          this.markSave(exerciseId, state);
        }
      });

    effect(() => {
      const id = Number(this.id());
      untracked(() => void this.load(id));
    });
  }

  ngOnDestroy(): void {
    this.subscription.unsubscribe();
  }

  private async load(id: number): Promise<void> {
    this.loading.set(true);
    try {
      this.setClass(await firstValueFrom(this.api.getClass(id)));
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo cargar la clase.'));
    } finally {
      this.loading.set(false);
    }
  }

  private setClass(detail: ClassDetail): void {
    this.klass.set(detail);
    const answers: Record<number, string> = {};
    for (const exercise of detail.exercises) {
      answers[exercise.id] = exercise.answer ?? '';
    }
    this.answers.set(answers);
    this.saveState.set({});
    if (detail.notice) {
      this.toast.show(detail.notice);
    }
  }

  private markSave(exerciseId: number, state: SaveState): void {
    this.saveState.update((current) => ({ ...current, [exerciseId]: state }));
  }

  resultClass(exercise: Exercise): string {
    const result = exercise.result?.result;
    if (!result) {
      return 'card exercise';
    }
    const suffix = result === 'correct' ? 'correct' : result === 'partially_correct' ? 'partial' : 'incorrect';
    return `card exercise result-${suffix}`;
  }

  onAnswer(exerciseId: number, answer: string, immediate = false): void {
    this.answers.update((current) => ({ ...current, [exerciseId]: answer }));
    this.markSave(exerciseId, 'saving');
    this.edits.next({ exerciseId, answer, immediate });
  }

  async submit(): Promise<void> {
    const c = this.klass();
    if (!c) {
      return;
    }
    const unanswered = c.exercises.length - this.answeredCount();
    if (unanswered > 0) {
      this.toast.show(`Enviaste la clase con ${unanswered} ejercicio(s) sin responder.`);
    }
    await this.run(() => this.api.submitClass(c.id, this.answers()));
    await this.auth.refreshMe().catch(() => undefined);
  }

  async retryGeneration(): Promise<void> {
    await this.run(() => this.api.retryGeneration(this.klass()!.id));
  }

  async retryEvaluation(): Promise<void> {
    const id = this.klass()!.id;
    this.busy.set(true);
    try {
      await firstValueFrom(this.api.processPending());
      this.setClass(await firstValueFrom(this.api.getClass(id)));
      if (this.klass()?.status === 'AWAITING_EVALUATION') {
        this.toast.show('Todavía no hay conexiones de IA disponibles.');
      }
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busy.set(false);
    }
  }

  async retake(): Promise<void> {
    await this.run(() => this.api.retakeClass(this.klass()!.id));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async appeal(exerciseId: number): Promise<void> {
    await this.run(() => this.api.appeal(this.klass()!.id, exerciseId));
  }

  private async run(request: () => Observable<ClassDetail>): Promise<void> {
    this.busy.set(true);
    try {
      this.setClass(await firstValueFrom(request()));
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busy.set(false);
    }
  }
}
