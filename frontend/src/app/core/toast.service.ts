import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  text: string;
  kind: 'info' | 'error' | 'success';
}

/** Avisos no bloqueantes (documento funcional §29: nada de modales con OK). */
@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([]);
  private nextId = 1;

  show(text: string, kind: Toast['kind'] = 'info', ms = 5000): void {
    const toast = { id: this.nextId++, text, kind };
    this.toasts.update((list) => [...list, toast]);
    setTimeout(() => this.dismiss(toast.id), ms);
  }

  error(text: string): void {
    this.show(text, 'error', 7000);
  }

  success(text: string): void {
    this.show(text, 'success');
  }

  dismiss(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }
}
