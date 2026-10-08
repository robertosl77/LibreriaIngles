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
import { LoadingDotsComponent } from '../../shared/ui/loading-dots.component';
import { PronunciationPracticeComponent } from '../../shared/pronunciation-practice.component';
import { STATUS_LABELS, scoreChip, statusChip } from '../../shared/status';

type SaveState = 'saving' | 'saved' | 'error';

const TYPE_LABELS: Record<Exercise['type'], string> = {
  fill_blank: 'Completar',
  multiple_choice: 'Opción múltiple',
  reading_multiple_choice: 'Lectura',
  rewrite: 'Reescribir',
  short_writing: 'Escritura',
  conversation: 'Conversación',
  dictation: 'Dictado',
  word_order: 'Ordenar palabras',
  dialogue_choice: 'Elegir la respuesta',
  read_aloud: 'Leer en voz alta',
  minimal_pairs: 'Sonidos parecidos',
  match_pairs: 'Emparejar',
  listen_form: 'Formulario escuchado',
  gap_text: 'Texto con huecos',
  error_correction: 'Corregir el error',
  word_stress: 'Sílaba fuerte'
};

/** T-183: tipos cuya respuesta tiene varias partes y se guarda como JSON. */
const STRUCTURED_TYPES = new Set<Exercise['type']>(['match_pairs', 'listen_form', 'gap_text']);
const INPUT_PLACEHOLDERS: Partial<Record<Exercise['type'], string>> = {
  rewrite: 'Escribí la oración completa',
  dictation: 'Escribí la oración que escuchaste',
  error_correction: 'Escribí la oración corregida'
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
    LoadingDotsComponent,
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

          @if (c.reducedFrom && c.reducedFrom > c.exercises.length && editable()) {
            <p class="banner banner-info small">
              Esta clase tiene {{ c.exercises.length }} ejercicios en lugar de {{ c.reducedFrom }}: el cupo de la IA
              estaba casi completo. Se mantuvieron los que refuerzan lo que más te cuesta.
            </p>
          }

          @if (c.kind === 'EXAM' && editable()) {
            <p class="banner banner-info small">
              <strong>Examen de nivel {{ c.targetLevel }}.</strong> {{ c.exercises.length }} ejercicios de todas las
              áreas, sin lecciones. Para aprobar: 70% en total y al menos 60% en cada área y en Ortografía. Tus
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
                Se aprueba con {{ r.passScore }}% en total y al menos {{ r.areaMinScore }}% en cada área y en Ortografía (línea vertical).
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
              Tus respuestas se guardan automáticamente. {{ answeredCount() }}/{{ visible().length }} respondidas.@if (practiceRunning()) { Tanda {{ c.practice!.batch }}. }
            </p>
          }

          @for (exercise of visible(); track exercise.id; let i = $index) {
            <article
              class="card exercise"
              [attr.id]="'ex-' + exercise.id"
              [class]="resultClass(exercise)"
              [class.form-locked]="formLocked()"
              [class.conversation-card]="exercise.type === 'conversation'"
              [class.conversation-start]="exercise.type === 'conversation' && (exercise.conversation?.turn ?? 1) === 1"
              [class.conversation-end]="exercise.type === 'conversation' && (exercise.conversation?.turn ?? 1) === (exercise.conversation?.total ?? 1)"
            >
              <header class="exercise-head">
                <span class="muted small">
                  @if (exercise.type === 'conversation') {
                    @if ((exercise.conversation?.turn ?? 1) === 1) {
                      {{ i + 1 }}. <strong>Conversación guiada</strong> · {{ exercise.conversation?.total ?? 1 }} turnos
                    } @else {
                      <strong>Turno {{ exercise.conversation?.turn ?? 1 }} de {{ exercise.conversation?.total ?? 1 }}</strong>
                    }
                    @if (exercise.presentation === 'LISTEN') { · <strong class="modality">Escucha</strong> }
                    @if (exercise.response === 'SPEAK') { · <strong class="modality">Habla</strong> }
                    · {{ exercise.skillName }}
                  } @else {
                    {{ i + 1 }}. {{ typeLabels[exercise.type] }}
                    @if (exercise.presentation === 'LISTEN') { · <strong class="modality">Escucha</strong> }
                    @if (exercise.response === 'SPEAK') { · <strong class="modality">Habla</strong> }
                    · {{ exercise.skillName }}
                  }
                </span>
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

              @if (exercise.instruction && exercise.type !== 'conversation') {
                <p class="instruction">{{ exercise.instruction }}</p>
              }
              @if (exercise.type === 'conversation') {
                <div class="conversation-turn-grid">
                  <section class="conversation-side partner-side">
                    <span class="speaker">Interlocutor</span>
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

                    @if ((editable() || c.status === 'COMPLETED') && !busy() && exercise.hasLesson && openPronunciationPractice() !== exercise.id) {
                      <div class="turn-help">
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
                      </div>
                    }
                  </section>

                  <div class="conversation-flow" aria-hidden="true">
                    <span>→</span>
                  </div>

                  <section class="conversation-side student-side">
                    <span class="speaker">Vos</span>
                    @if (editable()) {
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
                    } @else {
                      <strong>{{ exercise.answer || '(sin respuesta)' }}</strong>
                    }

                    @if (editable() && !busy() && exercise.response === 'SPEAK' && c.kind !== 'EXAM' && openLesson() !== exercise.id) {
                      <div class="turn-help">
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
                      </div>
                    }
                  </section>
                </div>
              } @else {
                @if (exercise.passage && (exercise.type !== 'gap_text' || !editable())) {
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
                <p class="question" [class.read-aloud-text]="exercise.type === 'read_aloud'">{{ exercise.question }}</p>
              }

              @if (exercise.type !== 'conversation' && (editable() || c.status === 'COMPLETED') && !busy() && exercise.hasLesson && openPronunciationPractice() !== exercise.id) {
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

              @if (exercise.type !== 'conversation' && editable() && !busy() && exercise.response === 'SPEAK' && c.kind !== 'EXAM' && openLesson() !== exercise.id) {
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

              @if (exercise.type !== 'conversation') {
                @if (editable()) {
                  @if (exercise.response === 'SPEAK') {
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
                      @case ('dialogue_choice') {
                        <ng-container *ngTemplateOutlet="options; context: { $implicit: exercise }" />
                      }
                      @case ('minimal_pairs') {
                        <ng-container *ngTemplateOutlet="options; context: { $implicit: exercise }" />
                      }
                      @case ('word_stress') {
                        <ng-container *ngTemplateOutlet="options; context: { $implicit: exercise }" />
                      }
                      @case ('word_order') {
                        <div class="tiles-answer" aria-label="Tu oración">
                          @for (index of picked()[exercise.id] ?? []; track $index; let pos = $index) {
                            <button class="tile picked" type="button" [disabled]="formLocked()" (click)="unpickTile(exercise, pos)">
                              {{ exercise.tiles?.[index] }}
                            </button>
                          } @empty {
                            <span class="muted small">Tocá las palabras en orden para armar la oración.</span>
                          }
                        </div>
                        <div class="tiles-bank" aria-label="Palabras disponibles">
                          @for (tile of exercise.tiles ?? []; track $index; let index = $index) {
                            <button
                              class="tile"
                              type="button"
                              [disabled]="formLocked() || isPicked(exercise.id, index)"
                              [class.used]="isPicked(exercise.id, index)"
                              (click)="pickTile(exercise, index)"
                            >{{ tile }}</button>
                          }
                        </div>
                      }
                      @case ('match_pairs') {
                        <div class="pairs-grid">
                          @for (left of exercise.pairs?.left ?? []; track left) {
                            <label class="pair-row">
                              <span class="pair-left" lang="en">{{ left }}</span>
                              <select
                                class="input"
                                [ngModel]="structured(exercise)[left] ?? ''"
                                (ngModelChange)="setPart(exercise, left, $event)"
                                [disabled]="formLocked()"
                              >
                                <option value="">Elegí…</option>
                                @for (right of exercise.pairs?.right ?? []; track right) {
                                  <option [value]="right">{{ right }}</option>
                                }
                              </select>
                            </label>
                          }
                        </div>
                      }
                      @case ('listen_form') {
                        <div class="form-fields">
                          @for (field of exercise.fields ?? []; track field) {
                            <label class="form-field">
                              <span>{{ field }}</span>
                              <input
                                class="input"
                                type="text"
                                autocomplete="off"
                                spellcheck="false"
                                [ngModel]="structured(exercise)[field] ?? ''"
                                (ngModelChange)="setPart(exercise, field, $event, false)"
                                [disabled]="formLocked()"
                              />
                            </label>
                          }
                        </div>
                      }
                      @case ('gap_text') {
                        <p class="gap-text" lang="en">
                          @for (segment of gapSegments(exercise); track $index; let gap = $index) {
                            <span>{{ segment }}</span>
                            @if (gap < gapSegments(exercise).length - 1) {
                              @if (exercise.options?.length) {
                                <select
                                  class="input gap-input"
                                  [attr.aria-label]="'Hueco ' + (gap + 1)"
                                  [ngModel]="gapValue(exercise, gap)"
                                  (ngModelChange)="setGap(exercise, gap, $event)"
                                  [disabled]="formLocked()"
                                >
                                  <option value="">({{ gap + 1 }})</option>
                                  @for (word of exercise.options; track word) {
                                    <option [value]="word">{{ word }}</option>
                                  }
                                </select>
                              } @else {
                                <input
                                  class="input gap-input"
                                  type="text"
                                  [attr.aria-label]="'Hueco ' + (gap + 1)"
                                  [ngModel]="gapValue(exercise, gap)"
                                  (ngModelChange)="setGap(exercise, gap, $event, false)"
                                  [disabled]="formLocked()"
                                />
                              }
                            }
                          }
                        </p>
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
                          [placeholder]="placeholders[exercise.type] ?? 'Palabra(s) que completan el espacio'"
                        />
                      }
                    }
                  }
                } @else {
                  <p class="your-answer">
                    <span class="muted small">Tu respuesta:</span>
                    <strong>{{ readableAnswer(exercise) || '(sin respuesta)' }}</strong>
                  </p>
                }
              }

              @if (exercise.result; as r) {
                <div class="feedback stack">
                  @if (r.feedback) { <p>{{ r.feedback }}</p> }
                  @if (r.ai; as ai) {
                    <p class="muted small">
                      Corrección realizada por {{ ai.providerLabel }}@if (ai.model) { · motor {{ ai.model }} }
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
                    <span class="appeal-row">
                      <button class="btn-link small" type="button" (click)="appeal(exercise.id)" [disabled]="busy()">
                        Creo que mi respuesta es correcta
                      </button>
                      @if (appealingId() === exercise.id) {
                        <app-loading-dots class="small" text="Revisando…" label="Revisando tu respuesta" />
                      }
                    </span>
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
                <span class="muted small">{{ answeredCount() }}/{{ visible().length }} respondidas</span>
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
              <div class="submit-actions">
                @if (practiceRunning()) {
                  <!-- T-214: Continuar = esta tanda se corrige en segundo plano y aparece la siguiente. -->
                  <button class="btn" type="button" (click)="continuePractice()" [disabled]="busy() || !allAnswered()">
                    @if (continuing()) { <span class="spinner"></span> Cargando… } @else { Continuar }
                  </button>
                }
                <button class="btn btn-primary" type="button" (click)="submit()" [disabled]="busy() || !allAnswered()">
                  @if (busy() && !continuing()) { <span class="spinner"></span> Corrigiendo… } @else { {{ c.kind === 'EXAM' ? 'Finalizar examen' : 'Finalizar y comprobar' }} }
                </button>
              </div>
            </div>
          }

          <p class="muted small">
            Creada {{ c.createdAt | date: 'dd/MM/yyyy HH:mm' }}
            @if (c.generationAi; as ai) {
              · {{ c.kind === 'EXAM' ? 'Examen' : 'Clase' }} realizada por el agente
              {{ ai.providerLabel }}@if (ai.model) { · motor {{ ai.model }} }
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
    .read-aloud-text { font-size: 1.3rem; font-weight: 600; padding: 0.6rem 0.8rem; background: var(--bg); border-radius: 0.6rem; }
    .tiles-answer, .tiles-bank { display: flex; flex-wrap: wrap; gap: 0.45rem; align-items: center; }
    .tiles-answer { min-height: 2.8rem; padding: 0.5rem; border: 1px dashed var(--border); border-radius: 0.6rem; }
    .tile {
      font: inherit; padding: 0.4rem 0.75rem; border: 1px solid var(--border); border-radius: 0.5rem;
      background: var(--surface); cursor: pointer;
    }
    .tile:hover:not(:disabled) { border-color: #111; }
    .tile.picked { background: #f3f6ff; border-color: #c9d6ff; }
    .tile.used { opacity: 0.35; }
    .tile:disabled { cursor: default; }
    .pairs-grid, .form-fields { display: flex; flex-direction: column; gap: 0.45rem; }
    .pair-row, .form-field { display: grid; grid-template-columns: minmax(6rem, 12rem) minmax(0, 1fr); gap: 0.6rem; align-items: center; }
    .pair-left { font-weight: 600; }
    .gap-text { margin: 0; line-height: 2.4; font-size: 1.05rem; }
    .gap-input { display: inline-block; width: auto; min-width: 6rem; margin: 0 0.25rem; padding: 0.2rem 0.4rem; }
    .conversation-card {
      border-color: #d9d5cb;
      background: linear-gradient(180deg, #fffefb, var(--surface));
    }
    .conversation-start {
      border-bottom-left-radius: 0;
      border-bottom-right-radius: 0;
      border-bottom-style: dashed;
      padding-bottom: 0.9rem;
      margin-bottom: -1rem;
      position: relative;
      z-index: 1;
    }
    .conversation-end {
      border-top-left-radius: 0;
      border-top-right-radius: 0;
      border-top: 0;
      padding-top: 1.05rem;
    }
    .conversation-end .exercise-head { padding-top: 0.1rem; }
    .conversation-turn-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 2.25rem minmax(0, 1fr);
      gap: 0.55rem;
      align-items: center;
    }
    .conversation-side {
      min-width: 0;
      padding: 0.72rem 0.82rem;
      border: 1px solid var(--border);
      border-radius: 0.8rem;
      display: flex;
      flex-direction: column;
      gap: 0.55rem;
      align-self: stretch;
    }
    .partner-side {
      background: #fbfaf6;
      border-bottom-left-radius: 0.25rem;
    }
    .student-side {
      background: #f6f8ff;
      border-bottom-right-radius: 0.25rem;
    }
    .conversation-flow {
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--muted);
      font-size: 1.35rem;
      font-weight: 700;
      align-self: center;
    }
    .conversation-flow span {
      display: grid;
      place-items: center;
      width: 1.9rem;
      height: 1.9rem;
      border: 1px solid var(--border);
      border-radius: 50%;
      background: var(--surface);
    }
    .turn-help { padding-top: 0.15rem; }
    .speaker { font-size: 0.75rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; }
    .chat-text { margin: 0; font-size: 1.05rem; line-height: 1.4; }
    .conversation-input { resize: vertical; background: var(--surface); }
    .chat-bubble.closing { max-width: 50%; padding: 0.7rem 0.85rem; border: 1px solid var(--border); border-radius: 0.75rem; background: var(--bg); display: flex; flex-direction: column; gap: 0.3rem; }
    @media (max-width: 720px) {
      .conversation-turn-grid { grid-template-columns: 1fr; }
      .conversation-flow { transform: rotate(90deg); }
      .conversation-start { margin-bottom: -0.75rem; }
      .chat-bubble.closing { max-width: 100%; }
    }
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
    .feedback .appeal-row { align-self: flex-start; display: inline-flex; align-items: center; gap: 0.5rem; }
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
    .submit-actions { display: flex; gap: 0.6rem; flex-wrap: wrap; justify-content: flex-end; }
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
  readonly placeholders = INPUT_PLACEHOLDERS;
  /** word_order: índices de las fichas elegidas, en orden, por ejercicio. */
  readonly picked = signal<Record<number, number[]>>({});
  readonly statusChip = statusChip;
  readonly scoreChip = scoreChip;

  readonly klass = signal<ClassDetail | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  /** T-204: ejercicio cuya corrección se está revisando (muestra los puntos de espera). */
  readonly appealingId = signal<number | null>(null);
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
  /** T-214: práctica en curso → solo se ven los ejercicios de la tanda actual (evita scroll). */
  readonly practiceRunning = computed(() => {
    const p = this.klass()?.practice;
    return !!p && !p.finished && this.editable();
  });
  readonly visible = computed(() => {
    const c = this.klass();
    if (!c) return [];
    if (!this.practiceRunning()) return c.exercises;
    return c.exercises.filter((exercise) => (exercise.batch ?? 1) === c.practice!.batch);
  });
  readonly continuing = signal(false);
  readonly answeredCount = computed(() => {
    const c = this.klass();
    if (!c) return 0;
    const answers = this.answers();
    const confirmed = this.confirmedSpeaking();
    return this.visible().filter((exercise) =>
      exercise.response === 'SPEAK'
        ? confirmed.has(exercise.id)
        : this.isAnswered(exercise, answers[exercise.id] ?? '')
    ).length;
  });

  /** Se puede finalizar recién cuando todos los ejercicios tienen respuesta (las habladas, confirmadas). */
  readonly allAnswered = computed(() => {
    const c = this.klass();
    return !!c && this.visible().length > 0 && this.answeredCount() === this.visible().length;
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
      this.scrollToLinkedExercise();
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo cargar la clase.'));
    } finally {
      this.loading.set(false);
    }
  }

  private scrollToLinkedExercise(): void {
    const fragment = window.location.hash.replace(/^#/, '');
    if (!/^ex-\d+$/.test(fragment)) return;
    // El ejercicio se renderiza después de actualizar la signal; esperamos al siguiente ciclo.
    setTimeout(() => {
      document.getElementById(fragment)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  private setClass(detail: ClassDetail): void {
    this.klass.set(detail);
    const answers: Record<number, string> = {};
    for (const exercise of detail.exercises) {
      answers[exercise.id] = exercise.answer ?? '';
    }
    this.answers.set(answers);
    this.picked.set(this.restorePicked(detail));
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

  // ---------------------------------------------------------------- T-183: tipos nuevos

  /** Una respuesta de varias partes cuenta como respondida cuando están todas. */
  isAnswered(exercise: Exercise, answer: string): boolean {
    if (!STRUCTURED_TYPES.has(exercise.type)) return Boolean(answer.trim());
    if (exercise.type === 'gap_text') {
      const gaps = this.gapSegments(exercise).length - 1;
      const values = this.parseList(answer);
      return gaps > 0 && values.length >= gaps && values.slice(0, gaps).every((v) => v.trim());
    }
    const keys = exercise.type === 'match_pairs' ? (exercise.pairs?.left ?? []) : (exercise.fields ?? []);
    const values = this.parseObject(answer);
    return keys.length > 0 && keys.every((k) => (values[k] ?? '').trim());
  }

  structured(exercise: Exercise): Record<string, string> {
    return this.parseObject(this.answers()[exercise.id] ?? '');
  }

  setPart(exercise: Exercise, key: string, value: string, immediate = true): void {
    const next = { ...this.structured(exercise), [key]: value };
    this.onAnswer(exercise.id, JSON.stringify(next), immediate);
  }

  gapSegments(exercise: Exercise): string[] {
    return (exercise.passage ?? '').split('___');
  }

  gapValue(exercise: Exercise, index: number): string {
    return this.parseList(this.answers()[exercise.id] ?? '')[index] ?? '';
  }

  setGap(exercise: Exercise, index: number, value: string, immediate = true): void {
    const gaps = this.gapSegments(exercise).length - 1;
    const values = this.parseList(this.answers()[exercise.id] ?? '');
    const next = Array.from({ length: gaps }, (_, i) => (i === index ? value : (values[i] ?? '')));
    this.onAnswer(exercise.id, JSON.stringify(next), immediate);
  }

  isPicked(exerciseId: number, index: number): boolean {
    return (this.picked()[exerciseId] ?? []).includes(index);
  }

  pickTile(exercise: Exercise, index: number): void {
    if (this.formLocked() || this.isPicked(exercise.id, index)) return;
    this.updatePicked(exercise, [...(this.picked()[exercise.id] ?? []), index]);
  }

  unpickTile(exercise: Exercise, position: number): void {
    if (this.formLocked()) return;
    const current = [...(this.picked()[exercise.id] ?? [])];
    current.splice(position, 1);
    this.updatePicked(exercise, current);
  }

  private updatePicked(exercise: Exercise, indexes: number[]): void {
    this.picked.update((all) => ({ ...all, [exercise.id]: indexes }));
    const tiles = exercise.tiles ?? [];
    // Respuesta completa recién cuando se usaron todas las fichas (antes no cuenta como respondida).
    const sentence = indexes.length === tiles.length ? indexes.map((i) => tiles[i]).join(' ') : '';
    this.onAnswer(exercise.id, sentence, true);
  }

  /** Reconstruye el orden de fichas desde la respuesta guardada (borrador o intento). */
  private restorePicked(detail: ClassDetail): Record<number, number[]> {
    const result: Record<number, number[]> = {};
    for (const exercise of detail.exercises) {
      if (exercise.type !== 'word_order' || !exercise.tiles || !exercise.answer) continue;
      const used = new Set<number>();
      const indexes: number[] = [];
      for (const word of exercise.answer.split(/\s+/)) {
        const index = exercise.tiles.findIndex((tile, i) => !used.has(i) && tile.toLowerCase() === word.toLowerCase());
        if (index < 0) break;
        used.add(index);
        indexes.push(index);
      }
      result[exercise.id] = indexes;
    }
    return result;
  }

  /** Respuesta legible (las de varias partes se guardan como JSON). */
  readableAnswer(exercise: Exercise): string {
    const answer = exercise.answer ?? '';
    if (!STRUCTURED_TYPES.has(exercise.type)) return answer;
    if (exercise.type === 'gap_text') {
      return this.parseList(answer).map((v, i) => `${i + 1}. ${v || '—'}`).join(' · ');
    }
    const joiner = exercise.type === 'match_pairs' ? ' = ' : ': ';
    return Object.entries(this.parseObject(answer))
      .map(([k, v]) => `${k}${joiner}${v || '—'}`)
      .join(' · ');
  }

  private parseObject(text: string): Record<string, string> {
    try {
      const value = JSON.parse(text);
      return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    } catch {
      return {};
    }
  }

  private parseList(text: string): string[] {
    try {
      const value = JSON.parse(text);
      return Array.isArray(value) ? value.map((v) => String(v ?? '')) : [];
    } catch {
      return [];
    }
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
    const missing = this.visible().find((exercise) =>
      exercise.response === 'SPEAK'
        ? !confirmed.has(exercise.id)
        : !this.isAnswered(exercise, answers[exercise.id] ?? '')
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
      await this.processSpeaking(c);

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

  /** T-214: "Continuar": esta tanda se guarda (se corrige en segundo plano) y aparece la siguiente. */
  async continuePractice(): Promise<void> {
    const c = this.klass();
    if (!c || !this.practiceRunning() || this.busy()) return;
    if (!this.allAnswered()) {
      this.toast.show('Respondé todos los ejercicios de esta tanda antes de continuar.');
      this.goToFirstMissing();
      return;
    }
    this.busy.set(true);
    this.continuing.set(true);
    try {
      await this.processSpeaking(c);
      const ids = new Set(this.visible().map((exercise) => exercise.id));
      const answers = Object.fromEntries(
        Object.entries(this.answers()).filter(([id]) => ids.has(Number(id)))
      );
      this.setClass(await firstValueFrom(this.api.continuePractice(c.id, answers)));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      this.toast.error(errorMessage(err, err instanceof Error ? err.message : undefined));
    } finally {
      this.continuing.set(false);
      this.busy.set(false);
    }
  }

  /** Recién al entregar salen del navegador los audios confirmados (solo los de lo que se ve).
   *  Cada audio se procesa como máximo una vez salvo que el alumno lo reemplace. */
  private async processSpeaking(c: ClassDetail): Promise<void> {
    for (const exercise of this.visible()) {
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
    this.appealingId.set(exerciseId);
    try {
      await this.run(() => this.api.appeal(this.klass()!.id, exerciseId));
    } finally {
      this.appealingId.set(null);
    }
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
