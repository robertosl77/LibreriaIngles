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
import { ClassDetail, Exercise, Lesson } from '../../core/models';
import { SpeakingAudioStore } from '../../core/speaking-audio.store';
import { ToastService } from '../../core/toast.service';
import { AudioPlayerComponent } from '../../shared/audio-player.component';
import { AudioRecorderComponent, RecordedAudio } from '../../shared/audio-recorder.component';
import { LessonPanelComponent } from '../../shared/lesson-panel.component';
import { PronunciationPracticeComponent } from '../../shared/pronunciation-practice.component';
import { STATUS_LABELS, scoreChip, statusChip } from '../../shared/status';

type SaveState = 'saving' | 'saved' | 'error';

const TYPE_LABELS: Record<Exercise['type'], string> = {
  fill_blank: 'Completar',
  multiple_choice: 'Opción múltiple',
  reading_multiple_choice: 'Lectura',
  rewrite: 'Reescribir',
  short_writing: 'Escritura',
  conversation: 'Conversación'
};

/** En el examen cada audio se puede escuchar dos veces (en la práctica, sin límite). */
const EXAM_MAX_PLAYS = 2;

const RESULT_LABELS: Record<string, string> = {
  correct: 'Correcto',
  partially_correct: 'Parcial',
  incorrect: 'Incorrecto'
};

@Component({
  selector: 'app-class',
  imports: [
    FormsModule,
    RouterLink,
    DatePipe,
    NgTemplateOutlet,
    LessonPanelComponent,
    PronunciationPracticeComponent,
    AudioPlayerComponent,
    AudioRecorderComponent
  ],
  template: `
    <main class="page stack">
      @if (loading()) {
        <p class="muted"><span class="spinner"></span> Cargando clase…</p>
      }
      @if (!loading() && klass(); as c) {
        <div class="page-header">
          <div>
            <p class="muted small">
              <a routerLink="/app">Inicio</a> · {{ c.kind === 'EXAM' ? 'Examen' : 'Clase' }} #{{ c.id }} · {{ c.targetLevel }}
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

          @if (c.kind === 'CLASS' && c.focus.length) {
            <section class="focus" aria-label="Qué refuerza esta clase">
              <p class="focus-title">Esta clase refuerza</p>
              <ul>
                @for (f of c.focus; track f.key) {
                  <li [class.topic]="f.kind === 'topic'"><strong>{{ f.name }}</strong><span class="muted">{{ ' · ' + f.reason }}</span></li>
                }
              </ul>
            </section>
          }

          @if (c.kind === 'EXAM' && editable()) {
            <p class="banner banner-info small">
              <strong>Examen de nivel {{ c.targetLevel }}.</strong> {{ c.exercises.length }} ejercicios de todas las
              áreas, sin lecciones. Para aprobar: 70% en total y al menos 60% en cada área. Tus
              respuestas se guardan solas; cuando termines, tocá <strong>Finalizar examen</strong>.
            </p>
          }

          @if (c.status === 'COMPLETED' && c.kind === 'EXAM' && c.examResult; as r) {
            <section class="card exam-result" [class.ok]="r.passed">
              <div class="exam-result-head">
                <div>
                  <p class="muted small">Resultado del examen</p>
                  <p class="big-number">{{ r.score }}%</p>
                  <p class="verdict">{{ r.passed ? '¡Aprobaste el nivel ' + c.targetLevel + '!' : 'No aprobado' }}</p>
                </div>
                <div class="row">
                  @if (c.certificateCode) {
                    <a class="btn btn-primary" [routerLink]="['/certificado', c.certificateCode]">Ver certificado</a>
                  }
                  <a class="btn" routerLink="/app">Volver al inicio</a>
                </div>
              </div>
              <ul class="area-bars">
                @for (area of examRows(r); track area.key) {
                  <li>
                    <span class="area-name">{{ area.name }}</span>
                    <span class="bar" [attr.aria-label]="area.name + ' ' + area.score + '%'">
                      <span class="fill" [class.low]="!area.passed" [style.width.%]="area.score"></span>
                      <span class="min" [style.left.%]="r.areaMinScore" title="Mínimo por área"></span>
                    </span>
                    <strong [class.error-text]="!area.passed">{{ area.score }}%</strong>
                  </li>
                }
              </ul>
              <p class="muted small">
                Se aprueba con {{ r.passScore }}% en total y al menos {{ r.areaMinScore }}% en cada área (línea vertical).
                @if (!r.passed) { Podés volver a rendirlo en 24 horas; mientras tanto, practicá las áreas marcadas. }
              </p>
            </section>
          }

          @if (c.status === 'COMPLETED' && c.kind !== 'EXAM') {
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
              Tus respuestas se guardan automáticamente. {{ answeredCount() }}/{{ c.exercises.length }} respondidas.
            </p>
          }

          @for (exercise of c.exercises; track exercise.id; let i = $index) {
            <article class="card exercise" [attr.id]="'ex-' + exercise.id" [class]="resultClass(exercise)" [class.form-locked]="formLocked()">
              <header class="exercise-head">
                <span class="muted small">{{ i + 1 }}. {{ typeLabels[exercise.type] }}@if (exercise.presentation === 'LISTEN') { · <strong class="modality">Escucha</strong> }@if (exercise.response === 'SPEAK') { · <strong class="modality">Habla</strong> } · {{ exercise.skillName }}</span>
                @if (editable() && saveState()[exercise.id]; as state) {
                  <span class="small muted">
                    @switch (state) {
                      @case ('saving') { Guardando… }
                      @case ('saved') { Guardado }
                      @case ('error') { <span class="error-text">No se pudo guardar</span> }
                    }
                  </span>
                }
                <span class="head-chips">
                  @if (exercise.assistance === 'LESSON') {
                    <span class="chip chip-lesson" title="Respondido después de consultar la lección">Con lección</span>
                  }
                  @if (exercise.result; as r) {
                    <span [class]="scoreChip(r.score)">{{ resultLabels[r.result || 'incorrect'] }} · {{ r.score }}%</span>
                  }
                </span>
              </header>

              @if (exercise.instruction) {
                <p class="instruction">{{ exercise.instruction }}</p>
              }
              @if (exercise.type === 'conversation') {
                <div class="conversation-thread">
                  <div class="chat-bubble partner">
                    <span class="speaker">Interlocutor · turno {{ exercise.conversation?.turn ?? 1 }}/{{ exercise.conversation?.total ?? 1 }}</span>
                    @if (exercise.presentation === 'LISTEN' && exercise.stimulus; as stimulus) {
                      <app-audio-player
                        [text]="stimulus.text"
                        [lang]="stimulus.lang"
                        [rate]="stimulus.rate"
                        [maxPlays]="c.kind === 'EXAM' && editable() ? examMaxPlays : null"
                        [allowSlow]="c.kind !== 'EXAM'"
                        [initialPlays]="exercise.signals.listenPlays ?? 0"
                        [disabled]="formLocked()"
                        (played)="recordListen(exercise, $event.slow)"
                      />
                      <span class="muted small">Escuchá el turno y respondé.</span>
                    } @else {
                      <p class="chat-text">{{ exercise.question }}</p>
                    }
                  </div>
                </div>
              } @else {
                @if (exercise.passage) {
                  <blockquote class="passage">{{ exercise.passage }}</blockquote>
                }
                @if (exercise.presentation === 'LISTEN' && exercise.stimulus; as stimulus) {
                  <app-audio-player
                    [text]="stimulus.text"
                    [lang]="stimulus.lang"
                    [rate]="stimulus.rate"
                    [maxPlays]="c.kind === 'EXAM' && editable() ? examMaxPlays : null"
                    [allowSlow]="c.kind !== 'EXAM'"
                    [initialPlays]="exercise.signals.listenPlays ?? 0"
                    [disabled]="formLocked()"
                    (played)="recordListen(exercise, $event.slow)"
                  />
                }
                <p class="question">{{ exercise.question }}</p>
              }

              @if ((editable() || c.status === 'COMPLETED') && !busy() && exercise.hasLesson && openPronunciationPractice() !== exercise.id) {
                @if (openLesson() === exercise.id && lessonFor(exercise); as lesson) {
                  <app-lesson-panel
                    [lesson]="lesson"
                    [registered]="editable() && exercise.assistance === 'LESSON'"
                    [editable]="editable()"
                    (closed)="closeLesson()"
                  />
                } @else {
                  <button
                    class="lesson-btn"
                    type="button"
                    (click)="toggleLesson(exercise)"
                    [disabled]="lessonLoading() === exercise.id"
                  >
                    @if (lessonLoading() === exercise.id) {
                      <span class="spinner"></span>
                    } @else {
                      <svg class="book" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5v-15Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H20v3H6.5A2.5 2.5 0 0 1 4 20.5Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
                    }
                    <span>{{ editable() ? 'Necesito lección' : 'Ver lección del tema' }}</span>
                  </button>
                }
              }

              @if (editable() && !busy() && exercise.response === 'SPEAK' && c.kind !== 'EXAM' && openLesson() !== exercise.id) {
                @if (openPronunciationPractice() === exercise.id) {
                  <app-pronunciation-practice
                    (closed)="closePronunciationPractice()"
                    (practiced)="recordPractice(exercise, $event.score)"
                  />
                } @else {
                  <button class="lesson-btn pronunciation-btn" type="button" (click)="togglePronunciationPractice(exercise.id)">
                    <svg class="sound" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                      <path d="M4 10v4h4l5 4V6L8 10H4Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
                      <path d="M16 9.2a4 4 0 0 1 0 5.6M18.5 6.8a7 7 0 0 1 0 10.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                    </svg>
                    <span>Practicar fonética</span>
                  </button>
                }
              }

              @if (editable()) {
                @if (exercise.type === 'conversation') {
                  <div class="chat-bubble student">
                    <span class="speaker">Vos</span>
                    @if (exercise.response === 'SPEAK') {
                      <app-audio-recorder
                        [busy]="formLocked() || audioSavingId() === exercise.id"
                        [confirmed]="confirmedSpeaking().has(exercise.id)"
                        (recordingStarted)="beginSpeaking(exercise.id)"
                        (pendingChange)="markPendingSpeaking(exercise.id, $event)"
                        (accepted)="confirmSpeaking(exercise, $event)"
                      />
                    } @else {
                      <textarea
                        class="input conversation-input"
                        rows="2"
                        [ngModel]="answers()[exercise.id]"
                        (ngModelChange)="onAnswer(exercise.id, $event)"
                        [disabled]="formLocked()"
                        placeholder="Respondé naturalmente en inglés…"
                      ></textarea>
                    }
                  </div>
                } @else if (exercise.response === 'SPEAK') {
                  <app-audio-recorder
                    [busy]="formLocked() || audioSavingId() === exercise.id"
                    [confirmed]="confirmedSpeaking().has(exercise.id)"
                    (recordingStarted)="beginSpeaking(exercise.id)"
                    (pendingChange)="markPendingSpeaking(exercise.id, $event)"
                    (accepted)="confirmSpeaking(exercise, $event)"
                  />
                } @else {
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
                      [disabled]="formLocked()"
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
                      [disabled]="formLocked()"
                      [placeholder]="exercise.type === 'rewrite' ? 'Escribí la oración completa' : 'Palabra(s) que completan el espacio'"
                    />
                  }
                }
                }
              } @else if (exercise.type === 'conversation') {
                <div class="chat-bubble student">
                  <span class="speaker">Vos</span>
                  <strong>{{ exercise.answer || '(sin respuesta)' }}</strong>
                </div>
              } @else {
                <p class="your-answer">
                  <span class="muted small">Tu respuesta:</span>
                  <strong>{{ exercise.answer || '(sin respuesta)' }}</strong>
                </p>
              }

              @if (exercise.result; as r) {
                <div class="feedback stack">
                  @if (r.feedback) { <p>{{ r.feedback }}</p> }
                  @if (r.ai; as ai) {
                    <p class="muted small">
                      Corrección realizada por {{ ai.providerLabel }} · motor {{ ai.model }}
                    </p>
                  }
                  @if (exercise.response === 'SPEAK') {
                    <div class="speaking-evaluation">
                      <div>
                        <strong>Contenido: {{ resultLabels[r.result || 'incorrect'] }} · {{ r.score }}%</strong>
                      </div>
                      @if (exercise.pronunciationResult; as pronunciation) {
                        <div class="pronunciation-result">
                          <strong>Pronunciación: {{ pronunciation.score }}%</strong>
                          <span class="muted small">
                            · estimada por {{ pronunciation.providerLabel || pronunciation.provider }}
                            @if (pronunciation.model) { · motor {{ pronunciation.model }} }
                          </span>
                          @for (word of pronunciation.words; track $index) {
                            @if (word.score < 70) {
                              <span class="small">· <strong>{{ word.word }} {{ word.score }}%</strong></span>
                            }
                          }
                        </div>
                      } @else {
                        <div class="pronunciation-result pronunciation-unavailable">
                          <strong>Pronunciación: no evaluada</strong>
                          <span class="muted small"> · no disponible con la conexión de IA usada (se estima con Gemini).</span>
                        </div>
                      }
                    </div>
                  }
                  @if (effortSummary(exercise); as effort) {
                    <p class="small muted effort">{{ effort }}</p>
                  }
                  @if (exercise.presentation === 'LISTEN' && exercise.stimulus) {
                    <p class="small transcript"><span class="muted">El audio decía: </span><em lang="en">“{{ exercise.stimulus.text }}”</em></p>
                  }
                  @if (r.correctAnswer && r.result !== 'correct') {
                    <p class="small"><span class="muted">Respuesta correcta: </span><strong>{{ r.correctAnswer }}</strong></p>
                  }
                  @for (err of r.errors; track $index) {
                    @if (err.explanation || err.correction) {
                      <p class="small error-line">
                        @if (err.fragment) { <s>{{ err.fragment }}</s> }
                        @if (err.correction) { → <strong>{{ err.correction }}</strong> }
                        @if ((err.occurrences ?? 1) > 1) { <span class="chip">×{{ err.occurrences }}</span> }
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
                @if (exercise.type === 'conversation' && exercise.conversation?.closing; as closing) {
                  <div class="chat-bubble partner closing">
                    <span class="speaker">Interlocutor</span>
                    <span>{{ closing }}</span>
                  </div>
                }
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
                    [disabled]="formLocked()"
                    (change)="onAnswer(exercise.id, option, true)"
                  />
                  {{ option }}
                </label>
              }
            </div>
          </ng-template>

          @if (editable()) {
            <div class="submit-bar">
              <div class="submit-status">
                <span class="muted small">{{ answeredCount() }}/{{ c.exercises.length }} respondidas</span>
                @if (!busy() && !allAnswered()) {
                  <span class="small missing">
                    @if (pendingSpeakingCount()) {
                      {{ pendingSpeakingCount() }} grabación(es) sin guardar ·
                    }
                    Respondé todos los ejercicios para finalizar.
                    <button class="btn-link small" type="button" (click)="goToFirstMissing()">Ir al primero pendiente</button>
                  </span>
                }
              </div>
              <button class="btn btn-primary" type="button" (click)="submit()" [disabled]="busy() || !allAnswered()">
                @if (busy()) { <span class="spinner"></span> Corrigiendo… } @else { {{ c.kind === 'EXAM' ? 'Finalizar examen' : 'Finalizar y comprobar' }} }
              </button>
            </div>
          }

          <p class="muted small">
            Creada {{ c.createdAt | date: 'dd/MM/yyyy HH:mm' }}
            @if (c.generationAi; as ai) {
              · {{ c.kind === 'EXAM' ? 'Examen' : 'Clase' }} realizada por el agente
              {{ ai.providerLabel }} · motor {{ ai.model }}
            } @else if (c.generatedBy) {
              · generada con {{ c.generatedBy }}
            }
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
    .exercise.form-locked input,
    .exercise.form-locked textarea,
    .exercise.form-locked .option { cursor: not-allowed; }
    .exercise.form-locked .option { opacity: 0.75; }
    .exercise-head { display: flex; gap: 0.6rem; align-items: center; justify-content: space-between; flex-wrap: wrap; }
    .instruction { margin: 0; font-weight: 600; }
    .question { margin: 0; font-size: 1.15rem; }
    .passage { margin: 0; padding: 0.8rem 1rem; background: var(--bg); border-radius: 0.6rem; line-height: 1.6; }
    .options { display: flex; flex-direction: column; gap: 0.4rem; }
    .option { display: flex; gap: 0.6rem; align-items: center; padding: 0.6rem 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; cursor: pointer; }
    .option.checked { border-color: #111; background: var(--bg); }
    .transcript em { font-style: normal; }
    .conversation-thread { display: flex; flex-direction: column; gap: 0.55rem; }
    .chat-bubble { max-width: min(88%, 42rem); padding: 0.75rem 0.9rem; border-radius: 1rem; display: flex; flex-direction: column; gap: 0.35rem; }
    .chat-bubble.partner { align-self: flex-start; background: var(--bg); border: 1px solid var(--border); border-bottom-left-radius: 0.3rem; }
    .chat-bubble.student { align-self: flex-end; margin-left: auto; background: var(--info-bg); border: 1px solid var(--border); border-bottom-right-radius: 0.3rem; width: min(88%, 42rem); }
    .chat-bubble.closing { margin-top: 0.2rem; }
    .speaker { font-size: 0.75rem; font-weight: 700; color: var(--muted); }
    .chat-text { margin: 0; font-size: 1.05rem; }
    .conversation-input { resize: vertical; background: var(--surface); }
    .lesson-btn {
      align-self: flex-start;
      display: inline-flex; align-items: center; gap: 0.4rem;
      padding: 0.35rem 0.8rem;
      font: inherit; font-size: 0.85rem; font-weight: 600;
      color: #2f4ab3; background: #f3f6ff;
      border: 1px solid #c9d6ff; border-radius: 999px;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s;
    }
    .lesson-btn:hover:not(:disabled) { background: #e6ecff; border-color: #9fb4f5; }
    .lesson-btn:focus-visible { outline: 2px solid #2f4ab3; outline-offset: 2px; }
    .lesson-btn:disabled { opacity: 0.6; cursor: wait; }
    .lesson-btn .book, .lesson-btn .sound { flex: none; }
    .pronunciation-btn { color: #6b3aa5; background: #faf5ff; border-color: #dcc7f2; }
    .pronunciation-btn:hover:not(:disabled) { background: #f4eaff; border-color: #c9a9e8; }
    .pronunciation-btn:focus-visible { outline-color: #6b3aa5; }
    .chip-lesson { background: #f3f6ff; color: #2f4ab3; border: 1px solid #c9d6ff; }
    .head-chips { display: flex; gap: 0.4rem; margin-left: auto; flex-wrap: wrap; }
    .your-answer { margin: 0; display: flex; gap: 0.5rem; align-items: baseline; flex-wrap: wrap; }
    .feedback { gap: 0.4rem; border-top: 1px solid var(--border); padding-top: 0.6rem; }
    .feedback p { margin: 0; }
    .speaking-evaluation { display: flex; flex-direction: column; gap: 0.45rem; }
    .pronunciation-result {
      display: flex; gap: 0.35rem; align-items: baseline; flex-wrap: wrap;
      padding: 0.5rem 0.65rem; background: #faf5ff; border: 1px solid #dcc7f2; border-radius: 0.5rem;
    }
    .pronunciation-unavailable { background: var(--bg); border-color: var(--border); }
    .suggestion { color: #5a3d00; }
    .feedback .btn-link { align-self: flex-start; }
    .error-text { color: var(--bad); }
    .exam-result { display: flex; flex-direction: column; gap: 0.9rem; }
    .exam-result.ok { border-color: #d8c48a; background: linear-gradient(180deg, #fffdf6, var(--surface)); }
    .exam-result p { margin: 0; }
    .exam-result-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; }
    .verdict { font-weight: 700; }
    .exam-result.ok .verdict { color: var(--ok); }
    .area-bars { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.5rem; }
    .modality { color: #2f4ab3; font-weight: 600; }
    .focus {
      border: 1px solid var(--warn-bg); background: #fffaf0; border-left: 4px solid var(--warn);
      border-radius: 0.6rem; padding: 0.7rem 0.9rem;
    }
    .focus-title { margin: 0 0 0.3rem; font-weight: 700; font-size: 0.8rem; letter-spacing: 0.04em; text-transform: uppercase; color: var(--warn); }
    .focus ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 0.2rem; }
    .focus li.topic strong { font-weight: 600; }
    .area-bars li { display: grid; grid-template-columns: minmax(7rem, 14rem) 1fr 3.5rem; align-items: center; gap: 0.8rem; }
    .area-bars strong { text-align: right; }
    .bar { position: relative; height: 0.6rem; border-radius: 999px; background: var(--info-bg); }
    .bar .fill { position: absolute; inset: 0 auto 0 0; border-radius: 999px; background: var(--ok); }
    .bar .fill.low { background: var(--bad); }
    .bar .min { position: absolute; top: -0.25rem; bottom: -0.25rem; width: 2px; background: var(--text); opacity: 0.5; }
    .score-card { display: flex; gap: 1.5rem; align-items: center; justify-content: space-between; flex-wrap: wrap; }
    .score-card p { margin: 0; }
    .history { display: flex; flex-direction: column; gap: 0.2rem; }
    .submit-status { display: flex; flex-direction: column; gap: 0.15rem; }
    .submit-status .missing { color: var(--warn); }
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
  private readonly speakingAudio = inject(SpeakingAudioStore);
  private readonly toast = inject(ToastService);

  readonly labels = STATUS_LABELS;
  readonly typeLabels = TYPE_LABELS;
  readonly examMaxPlays = EXAM_MAX_PLAYS;
  readonly resultLabels = RESULT_LABELS;
  readonly statusChip = statusChip;
  readonly scoreChip = scoreChip;

  readonly klass = signal<ClassDetail | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly answers = signal<Record<number, string>>({});
  readonly saveState = signal<Record<number, SaveState>>({});
  /** Lecciones ya cargadas, por skill: una sola llamada por tema. */
  readonly lessons = signal<Record<string, Lesson>>({});
  readonly openLesson = signal<number | null>(null);
  readonly openPronunciationPractice = signal<number | null>(null);
  readonly lessonLoading = signal<number | null>(null);
  readonly audioSavingId = signal<number | null>(null);
  readonly confirmedSpeaking = signal<Set<number>>(new Set());
  /** Grabaciones hechas pero no confirmadas: no cuentan como respuesta. */
  readonly pendingSpeaking = signal<Set<number>>(new Set());
  readonly pendingSpeakingCount = computed(
    () => [...this.pendingSpeaking()].filter((id) => !this.confirmedSpeaking().has(id)).length
  );

  readonly editable = computed(() => {
    const status = this.klass()?.status;
    return status === 'READY' || status === 'IN_PROGRESS';
  });
  /** Desde que se envía a corregir, ninguna interacción puede alterar la evidencia. */
  readonly formLocked = computed(() => this.busy() || !this.editable());
  readonly answeredCount = computed(() => {
    const c = this.klass();
    if (!c) return 0;
    const answers = this.answers();
    const confirmed = this.confirmedSpeaking();
    return c.exercises.filter((exercise) =>
      exercise.response === 'SPEAK'
        ? confirmed.has(exercise.id)
        : Boolean((answers[exercise.id] ?? '').trim())
    ).length;
  });

  /** Se puede finalizar recién cuando todos los ejercicios tienen respuesta (las habladas, confirmadas). */
  readonly allAnswered = computed(() => {
    const c = this.klass();
    return !!c && c.exercises.length > 0 && this.answeredCount() === c.exercises.length;
  });

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
    this.confirmedSpeaking.set(new Set());
    this.pendingSpeaking.set(new Set());
    if (detail.status === 'READY' || detail.status === 'IN_PROGRESS') {
      void this.restoreSpeakingAudio(detail);
    } else {
      void this.speakingAudio.clearAttempt(detail.id, detail.currentAttempt).catch(() => undefined);
    }
    this.saveState.set({});
    this.openLesson.set(null);
    this.openPronunciationPractice.set(null);
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
    if (this.formLocked()) return;
    this.answers.update((current) => ({ ...current, [exerciseId]: answer }));
    this.markSave(exerciseId, 'saving');
    this.edits.next({ exerciseId, answer, immediate });
  }

  async beginSpeaking(exerciseId: number): Promise<void> {
    if (this.formLocked()) return;
    const c = this.klass();
    // Volver a grabar una respuesta ya guardada es señal de esfuerzo en Speaking (T-046 v2).
    if (c && this.confirmedSpeaking().has(exerciseId) && this.editable()) {
      this.api.recordSignal(c.id, exerciseId, { kind: 'retake' }).subscribe({
        next: (response) => this.updateSignals(exerciseId, response.signals),
        error: () => undefined
      });
    }
    this.confirmedSpeaking.update((current) => {
      const next = new Set(current);
      next.delete(exerciseId);
      return next;
    });
    if (!c) return;

    // Si un envío anterior alcanzó a procesar este audio pero no llegó a cerrar
    // la clase, una nueva toma invalida ese borrador derivado sin gastar IA.
    try {
      const stored = await this.speakingAudio.get(c.id, c.currentAttempt, exerciseId);
      if (stored?.processed) {
        await this.speakingAudio.markUnprocessed(c.id, c.currentAttempt, exerciseId);
        await firstValueFrom(this.api.saveAnswer(c.id, exerciseId, ''));
      }
    } catch {
      // La nueva grabación puede continuar: al confirmar se reemplazará el audio local.
    }
  }

  async confirmSpeaking(exercise: Exercise, recording: RecordedAudio): Promise<void> {
    if (this.formLocked()) return;
    const c = this.klass();
    if (!c || exercise.response !== 'SPEAK') return;

    this.audioSavingId.set(exercise.id);
    this.markSave(exercise.id, 'saving');
    try {
      await this.speakingAudio.put(c.id, c.currentAttempt, exercise.id, recording);
      this.confirmedSpeaking.update((current) => new Set(current).add(exercise.id));
      this.markSave(exercise.id, 'saved');

    } catch (err) {
      this.markSave(exercise.id, 'error');
      this.toast.error(
        err instanceof Error ? err.message : 'No se pudo guardar temporalmente la grabación.'
      );
    } finally {
      this.audioSavingId.set(null);
    }
  }

  private async restoreSpeakingAudio(detail: ClassDetail): Promise<void> {
    const restored = new Set<number>();
    try {
      for (const exercise of detail.exercises) {
        if (exercise.response !== 'SPEAK') continue;
        const stored = await this.speakingAudio.get(
          detail.id,
          detail.currentAttempt,
          exercise.id
        );
        if (stored) restored.add(exercise.id);
      }
      if (
        this.klass()?.id === detail.id &&
        this.klass()?.currentAttempt === detail.currentAttempt
      ) {
        this.confirmedSpeaking.set(restored);
      }
    } catch {
      this.toast.error('No se pudieron recuperar las grabaciones guardadas en este navegador.');
    }
  }

  /** Áreas + dimensiones visibles + modalidades transversales en el resultado del examen. */
  examRows(result: NonNullable<ClassDetail['examResult']>) {
    return [
      ...result.areas,
      ...(result.dimensions ?? []).map((d) => ({ ...d, key: 'dimension-' + d.key })),
      ...(result.modalities ?? []).map((m) => ({
        ...m,
        key: 'modality-' + m.key,
        name: m.name + (m.key === 'LISTEN' ? ' (todo lo escuchado)' : ' (todo lo hablado)')
      }))
    ];
  }

  lessonFor(exercise: Exercise): Lesson | null {
    return exercise.skillKey ? (this.lessons()[exercise.skillKey] ?? null) : null;
  }

  closeLesson(): void {
    this.openLesson.set(null);
  }

  togglePronunciationPractice(exerciseId: number): void {
    if (this.formLocked()) return;
    this.openLesson.set(null);
    this.openPronunciationPractice.update((current) => current === exerciseId ? null : exerciseId);
  }

  closePronunciationPractice(): void {
    this.openPronunciationPractice.set(null);
  }

  /** "Necesito lección": se abre dentro del ejercicio; al cerrarla sigue respondiendo ahí. */
  async toggleLesson(exercise: Exercise): Promise<void> {
    // Corregida: la lección se puede leer (no registra ayuda). Enviando/corrigiendo: bloqueado.
    if (this.busy() || (this.formLocked() && this.klass()?.status !== 'COMPLETED')) return;
    const c = this.klass();
    if (!c) {
      return;
    }
    const alreadyRegistered = !this.editable() || exercise.assistance === 'LESSON';
    if (this.lessonFor(exercise) && alreadyRegistered) {
      this.openLesson.set(exercise.id);
      return;
    }
    this.openPronunciationPractice.set(null);
    this.lessonLoading.set(exercise.id);
    try {
      const response = await firstValueFrom(this.api.lesson(c.id, exercise.id));
      this.lessons.update((current) => ({ ...current, [response.lesson.skillKey]: response.lesson }));
      if (response.registered) {
        this.klass.update((detail) =>
          detail
            ? {
                ...detail,
                status: detail.status === 'READY' ? 'IN_PROGRESS' : detail.status,
                exercises: detail.exercises.map((e) =>
                  e.id === exercise.id ? { ...e, assistance: 'LESSON' } : e
                )
              }
            : detail
        );
      }
      this.openLesson.set(exercise.id);
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo cargar la lección.'));
    } finally {
      this.lessonLoading.set(null);
    }
  }

  /** Evidencia de Listening (T-034): cada escucha, y si fue en modo lento. */
  recordListen(exercise: Exercise, slow: boolean): void {
    const c = this.klass();
    if (!c || !this.editable()) return;
    this.api.recordSignal(c.id, exercise.id, { kind: 'listen', slow }).subscribe({
      next: (response) => this.updateSignals(exercise.id, response.signals),
      error: () => undefined
    });
  }

  /** Evidencia de Pronunciation (T-034): cada intento de práctica. */
  recordPractice(exercise: Exercise, score: number): void {
    const c = this.klass();
    if (!c || !this.editable()) return;
    this.api.recordSignal(c.id, exercise.id, { kind: 'practice', score }).subscribe({
      next: (response) => this.updateSignals(exercise.id, response.signals),
      error: () => undefined
    });
  }

  private updateSignals(exerciseId: number, signals: Exercise['signals']): void {
    this.klass.update((detail) =>
      detail
        ? { ...detail, exercises: detail.exercises.map((e) => (e.id === exerciseId ? { ...e, signals } : e)) }
        : detail
    );
  }

  /** Resumen del esfuerzo, visible en la corrección. */
  effortSummary(exercise: Exercise): string | null {
    const s = exercise.signals ?? {};
    const parts: string[] = [];
    if (exercise.presentation === 'LISTEN' && s.listenPlays) {
      const slow = s.listenSlowPlays ? ` (${s.listenSlowPlays} en lento)` : '';
      parts.push(`Escuchaste el audio ${s.listenPlays} ${s.listenPlays === 1 ? 'vez' : 'veces'}${slow}`);
    }
    const trials = s.practiceScores ?? [];
    if (trials.length) {
      parts.push(
        `practicaste la pronunciación ${trials.length} ${trials.length === 1 ? 'vez' : 'veces'} (${trials[0]}% → ${trials[trials.length - 1]}%)`
      );
    }
    if (exercise.response === 'SPEAK' && s.speakRetakes) {
      const takes = s.speakRetakes + 1;
      parts.push(`grabaste tu respuesta ${takes} veces`);
    }
    if (!parts.length) return null;
    const text = parts.join(' · ');
    return text.charAt(0).toUpperCase() + text.slice(1) + '.';
  }

  markPendingSpeaking(exerciseId: number, pending: boolean): void {
    this.pendingSpeaking.update((current) => {
      const next = new Set(current);
      if (pending) next.add(exerciseId);
      else next.delete(exerciseId);
      return next;
    });
  }

  goToFirstMissing(): void {
    const c = this.klass();
    if (!c) return;
    const answers = this.answers();
    const confirmed = this.confirmedSpeaking();
    const missing = c.exercises.find((exercise) =>
      exercise.response === 'SPEAK'
        ? !confirmed.has(exercise.id)
        : !(answers[exercise.id] ?? '').trim()
    );
    if (missing) {
      document.getElementById('ex-' + missing.id)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  async submit(): Promise<void> {
    const c = this.klass();
    if (!c || !this.editable() || this.busy()) return;

    if (!this.allAnswered()) {
      this.toast.show('Respondé todos los ejercicios antes de finalizar.');
      this.goToFirstMissing();
      return;
    }

    this.busy.set(true);
    try {
      // Recién al entregar la clase salen del navegador los audios confirmados.
      // Cada audio se procesa como máximo una vez salvo que el alumno lo reemplace.
      for (const exercise of c.exercises) {
        if (exercise.response !== 'SPEAK' || !this.confirmedSpeaking().has(exercise.id)) {
          continue;
        }
        const stored = await this.speakingAudio.get(c.id, c.currentAttempt, exercise.id);
        if (!stored) {
          throw new Error('Falta una grabación confirmada. Volvé a grabar ese ejercicio.');
        }
        if (!stored.processed) {
          const result = await firstValueFrom(
            this.api.processSpeakingAnswer(
              c.id,
              exercise.id,
              stored.blob,
              stored.durationMs
            )
          );
          await this.speakingAudio.markProcessed(c.id, c.currentAttempt, exercise.id);
          if (result.switched) {
            this.toast.show('Se cambió automáticamente el proveedor para transcribir un audio.');
          }
        }
      }

      const detail = await firstValueFrom(this.api.submitClass(c.id, this.answers()));
      await this.speakingAudio.clearAttempt(c.id, c.currentAttempt);
      this.setClass(detail);
      await this.auth.refreshMe().catch(() => undefined);
    } catch (err) {
      this.toast.error(errorMessage(err, err instanceof Error ? err.message : undefined));
    } finally {
      this.busy.set(false);
    }
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
