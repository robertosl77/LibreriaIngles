import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../core/api.service';
import { ExamStatus } from '../core/models';
import { ToastService } from '../core/toast.service';

/** Examen de aprobación del nivel actual (T-024): requisitos, rendir, resultado, certificado. */
@Component({
  selector: 'app-exam-card',
  imports: [RouterLink, DatePipe],
  template: `
    @if (status(); as s) {
      @if (s.available) {
        <section class="card exam" [class.passed]="s.passed">
          <div class="exam-head">
            <div>
              <p class="eyebrow">Examen de nivel</p>
              <h2>
                @if (s.passed) { Aprobaste el nivel {{ s.level }} } @else { Examen {{ s.level }} }
              </h2>
            </div>
            <span class="seal" aria-hidden="true">{{ s.level }}</span>
          </div>

          @if (s.passed) {
            <p class="muted">
              Tu certificado de Librería Inglés ya está disponible.
              @if (s.nextLevel; as next) {
                @if (next.available) {
                  Podés seguir con {{ next.level }}.
                } @else {
                  El nivel {{ next.level }} llega próximamente.
                }
              }
            </p>
            <div class="row">
              <a class="btn btn-primary" [routerLink]="['/certificado', s.certificateCode]">Ver certificado</a>
              @if (s.nextLevel?.available) {
                <a class="btn" routerLink="/app/nivel">Cambiar a {{ s.nextLevel?.level }}</a>
              }
            </div>
          } @else if (s.openExamId) {
            <p class="muted">Tenés un examen en curso. Tus respuestas se guardan solas.</p>
            <div class="row">
              <a class="btn btn-primary" [routerLink]="['/app/clase', s.openExamId]">Continuar examen</a>
            </div>
          } @else {
            @if (s.lastExam?.result; as last) {
              <p class="last">
                Último intento: <strong>{{ last.score }}%</strong> · no aprobado.
                @for (area of last.areas; track area.key) {
                  @if (!area.passed) {
                    <span class="chip chip-bad">{{ area.name }} {{ area.score }}%</span>
                  }
                }
              </p>
            }

            @if (s.cooldownUntil) {
              <p class="muted small">Podés volver a rendirlo desde el {{ s.cooldownUntil | date: 'dd/MM HH:mm' }}. Mientras tanto, seguí practicando.</p>
            } @else if (s.eligible) {
              <p class="muted">
                Tu práctica muestra que estás listo. Son {{ s.rules?.exercises }} ejercicios de todas
                las áreas, sin lecciones. Para aprobar: {{ s.rules?.passScore }}% en total y al menos
                {{ s.rules?.areaMinScore }}% en cada área.
              </p>
            } @else {
              <p class="muted small">Se habilita cuando tu práctica del nivel sea suficiente:</p>
            }

            @if (!s.eligible) {
              <ul class="checks">
                @for (check of s.checks; track check.key) {
                  <li [class.ok]="check.ok">
                    <span class="tick" aria-hidden="true">{{ check.ok ? '✓' : '' }}</span>
                    <span>{{ check.label }} <span class="muted small">· {{ check.detail }}</span></span>
                  </li>
                }
              </ul>
            }

            @if (s.canStart) {
              <div class="row">
                <button class="btn btn-primary" type="button" (click)="start()" [disabled]="starting()">
                  @if (starting()) { <span class="spinner"></span> Armando examen… } @else { Rendir examen {{ s.level }} }
                </button>
              </div>
            }
          }
        </section>
      }
    }
  `,
  styles: `
    .exam { display: flex; flex-direction: column; gap: 0.7rem; }
    .exam p { margin: 0; }
    .exam.passed { border-color: #d8c48a; background: linear-gradient(180deg, #fffdf6, var(--surface)); }
    .exam-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
    .exam-head h2 { margin: 0.1rem 0 0; }
    .eyebrow { font-size: 0.75rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); }
    .seal {
      width: 3rem; height: 3rem; border-radius: 50%; flex: none;
      display: inline-flex; align-items: center; justify-content: center;
      font-weight: 700; border: 2px solid var(--border); color: var(--muted);
    }
    .passed .seal { border-color: #b8943c; color: #8a6a1f; background: #fbf3dc; }
    .checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 0.35rem; }
    .checks li { display: flex; gap: 0.6rem; align-items: center; }
    .tick {
      width: 1.3rem; height: 1.3rem; border-radius: 50%; flex: none; font-size: 0.75rem; font-weight: 700;
      display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--border);
    }
    .checks li.ok .tick { background: var(--ok-bg); color: var(--ok); border-color: transparent; }
    .last { display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; }
  `
})
export class ExamCardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  readonly status = signal<ExamStatus | null>(null);
  readonly starting = signal(false);

  async ngOnInit(): Promise<void> {
    try {
      this.status.set(await firstValueFrom(this.api.examStatus()));
    } catch {
      this.status.set(null);
    }
  }

  async start(): Promise<void> {
    this.starting.set(true);
    try {
      const exam = await firstValueFrom(this.api.createExam());
      if (exam.notice) {
        this.toast.show(exam.notice);
      }
      await this.router.navigate(['/app/clase', exam.id]);
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo armar el examen.'));
    } finally {
      this.starting.set(false);
    }
  }
}
