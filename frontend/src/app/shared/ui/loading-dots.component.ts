import { Component, input } from '@angular/core';

/** Tres puntos que se agrandan y achican en secuencia: "trabajando" discreto (T-204). */
@Component({
  selector: 'app-loading-dots',
  template: `
    <span class="dots" role="status" [attr.aria-label]="label()">
      <span></span><span></span><span></span>
    </span>
    @if (text()) { <span class="text">{{ text() }}</span> }
  `,
  styles: `
    :host { display: inline-flex; align-items: center; gap: 0.4rem; vertical-align: middle; }
    .dots { display: inline-flex; align-items: center; gap: 0.22rem; height: 0.8rem; }
    .dots span {
      width: 0.32rem; height: 0.32rem; border-radius: 50%;
      background: currentColor; opacity: 0.45;
      animation: pulse 1.2s ease-in-out infinite;
    }
    .dots span:nth-child(2) { animation-delay: 0.2s; }
    .dots span:nth-child(3) { animation-delay: 0.4s; }
    .text { font-size: 0.85em; color: var(--muted); }
    @keyframes pulse {
      0%, 60%, 100% { transform: scale(1); opacity: 0.45; }
      30% { transform: scale(1.7); opacity: 1; }
    }
    @media (prefers-reduced-motion: reduce) { .dots span { animation: none; } }
  `
})
export class LoadingDotsComponent {
  readonly text = input<string>('');
  readonly label = input<string>('Procesando');
}
