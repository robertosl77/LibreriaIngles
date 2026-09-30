import { Component, input, output } from '@angular/core';

import { Lesson } from '../core/models';

/** Lección del tema, mostrada dentro del ejercicio (T-020): el alumno no sale de la clase. */
@Component({
  selector: 'app-lesson-panel',
  template: `
    @let l = lesson();
    <section class="lesson" aria-label="Lección del tema">
      <header class="lesson-head">
        <div>
          <p class="eyebrow">Lección · {{ l.topic }}</p>
          <h3>{{ l.title }}</h3>
        </div>
      </header>

      @if (l.explanation) {
        <p>{{ l.explanation }}</p>
      }

      @if (l.rules.length) {
        <ul class="rules">
          @for (rule of l.rules; track $index) {
            <li>{{ rule }}</li>
          }
        </ul>
      }

      @if (l.examples.length) {
        <div class="block">
          <p class="label">Ejemplos</p>
          @for (ex of l.examples; track $index) {
            <p class="example">
              <strong lang="en">{{ ex.en }}</strong>
              @if (ex.es) { <span class="muted"> — {{ ex.es }}</span> }
            </p>
          }
        </div>
      }

      @if (l.commonMistakes.length) {
        <div class="block">
          <p class="label">Errores típicos</p>
          @for (m of l.commonMistakes; track $index) {
            <p class="mistake">
              <span class="wrong" lang="en">✗ {{ m.wrong }}</span>
              <span class="right" lang="en">✓ {{ m.right }}</span>
              @if (m.why) { <span class="muted small">{{ m.why }}</span> }
            </p>
          }
        </div>
      }

      @if (l.tip) {
        <p class="tip">💡 {{ l.tip }}</p>
      }

      <footer class="lesson-foot">
        @if (registered()) {
          <span class="muted small">
            Este ejercicio queda marcado como respondido con lección: suma práctica, pero cuenta
            menos para el dominio del tema.
          </span>
        }
        <button class="btn btn-sm" type="button" (click)="closed.emit()">
          {{ editable() ? 'Entendido, volver al ejercicio' : 'Cerrar lección' }}
        </button>
      </footer>
    </section>
  `,
  styles: `
    .lesson {
      display: flex; flex-direction: column; gap: 0.6rem;
      background: #f3f6ff; border: 1px solid #c9d6ff; border-radius: 0.6rem; padding: 0.9rem 1rem;
    }
    .lesson p, .lesson h3 { margin: 0; }
    .eyebrow { font-size: 0.75rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: #2f4ab3; }
    .lesson h3 { font-size: 1.05rem; }
    .rules { margin: 0; padding-left: 1.2rem; display: flex; flex-direction: column; gap: 0.2rem; }
    .block { display: flex; flex-direction: column; gap: 0.3rem; }
    .label { font-weight: 600; font-size: 0.85rem; }
    .mistake { display: flex; flex-direction: column; gap: 0.1rem; }
    .wrong { color: var(--bad); text-decoration: line-through; }
    .right { color: var(--ok); font-weight: 600; }
    .lesson-foot { display: flex; gap: 0.8rem; align-items: center; justify-content: space-between; flex-wrap: wrap; }
    .lesson-foot .btn { margin-left: auto; }
  `
})
export class LessonPanelComponent {
  readonly lesson = input.required<Lesson>();
  readonly registered = input(false);
  readonly editable = input(true);
  readonly closed = output<void>();
}
