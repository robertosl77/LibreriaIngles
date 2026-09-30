import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { ToastService } from './core/toast.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  template: `
    <router-outlet />
    <div class="toasts" aria-live="polite">
      @for (toast of toasts.toasts(); track toast.id) {
        <div class="toast" [class]="'toast toast-' + toast.kind">
          <span>{{ toast.text }}</span>
          <button type="button" aria-label="Cerrar" (click)="toasts.dismiss(toast.id)">×</button>
        </div>
      }
    </div>
  `,
  styles: `
    .toasts {
      position: fixed;
      top: 4.5rem;
      right: 1rem;
      left: 1rem;
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 0.5rem;
      pointer-events: none;
      z-index: 50;
    }
    .toast {
      pointer-events: auto;
      max-width: 420px;
      display: flex;
      gap: 0.8rem;
      align-items: flex-start;
      padding: 0.8rem 1rem;
      border-radius: 0.8rem;
      background: #161616;
      color: #fff;
      box-shadow: 0 8px 30px rgb(0 0 0 / 0.15);
      font-size: 0.92rem;
    }
    .toast-error { background: #b3261e; }
    .toast-success { background: #0f7a4a; }
    .toast button {
      border: 0;
      background: transparent;
      color: inherit;
      font-size: 1.1rem;
      cursor: pointer;
      line-height: 1;
    }
  `
})
export class AppComponent {
  readonly toasts = inject(ToastService);
}
