import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { BankReviewItem } from '../../core/models';
import { ToastService } from '../../core/toast.service';

/** T-216: ejercicios del banco reportados por alumnos. No se sirven hasta que SrMacros decide. */
@Component({
  selector: 'app-bank-review',
  imports: [DatePipe, FormsModule],
  template: `
    <section class="card stack">
      <div>
        <h2>Ejercicios en revisión</h2>
        <p class="muted small">
          Cuando 3 alumnos distintos reportan un ejercicio («se repite» o «está mal»), deja de mostrarse y
          espera tu decisión acá. Los más reportados aparecen primero.
        </p>
      </div>
      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else if (items().length === 0) {
        <p class="muted">No hay ejercicios para revisar.</p>
      } @else {
        <ul class="list">
          @for (item of items(); track item.id) {
            <li class="list-item review">
              <div class="stack-sm">
                <div class="row">
                  <span class="chip chip-warn">{{ item.wrongReports }} «está mal»</span>
                  <span class="chip">{{ item.repeatReports }} «se repite»</span>
                  <span class="muted small">{{ item.level }} · {{ item.skillKey }} · {{ item.type }} · servido {{ item.timesServed }} veces
                    @if (item.appeals) { · {{ item.appealsAccepted }}/{{ item.appeals }} reclamos aceptados }</span>
                </div>
                @if (item.instruction) { <p class="small"><strong>{{ item.instruction }}</strong></p> }
                <p>{{ item.prompt }}</p>
                @if (item.options?.length) { <p class="small muted">Opciones: {{ item.options!.join(' · ') }}</p> }
                <label class="small field">
                  Respuestas correctas (una por línea)
                  <textarea class="input" rows="2" [(ngModel)]="edits[item.id]"></textarea>
                </label>
                <details class="small">
                  <summary>{{ item.reports.length }} reporte(s)</summary>
                  @for (r of item.reports; track $index) {
                    <div class="muted">
                      {{ r.reason === 'WRONG' ? 'Está mal' : 'Se repite' }} · {{ r.at | date: 'dd/MM HH:mm' }}
                      · {{ r.email || 'alumno' }}
                      @if (r.reporterTotal > 3) { <span class="chip chip-warn">reportó {{ r.reporterTotal }} en total</span> }
                    </div>
                  }
                </details>
              </div>
              <div class="row actions">
                <button class="btn btn-sm" type="button" (click)="decide(item.id, 'ACTIVATE')" [disabled]="busy()">Reactivar</button>
                <button class="btn btn-sm" type="button" (click)="decide(item.id, 'FIX')" [disabled]="busy()">Corregir y reactivar</button>
                <button class="btn btn-sm danger" type="button" (click)="decide(item.id, 'RETIRE')" [disabled]="busy()">Retirar</button>
              </div>
            </li>
          }
        </ul>
      }
    </section>
  `,
  styles: `
    .review { flex-direction: column; align-items: stretch; gap: 0.6rem; }
    .stack-sm { display: flex; flex-direction: column; gap: 0.35rem; }
    .actions { gap: 0.5rem; justify-content: flex-end; }
    .danger { color: var(--bad); }
    textarea { width: 100%; }
  `
})
export class BankReviewComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly items = signal<BankReviewItem[]>([]);
  readonly loading = signal(true);
  readonly busy = signal(false);
  edits: Record<number, string> = {};

  async ngOnInit(): Promise<void> {
    try {
      this.setItems(await firstValueFrom(this.api.bankReview()));
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  async decide(id: number, action: 'ACTIVATE' | 'RETIRE' | 'FIX'): Promise<void> {
    this.busy.set(true);
    try {
      const answers = action === 'FIX' ? (this.edits[id] || '').split('\n') : undefined;
      this.setItems(await firstValueFrom(this.api.bankDecision(id, action, answers)));
      this.toast.show(action === 'RETIRE' ? 'Ejercicio retirado.' : 'Ejercicio reactivado.');
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busy.set(false);
    }
  }

  private setItems(items: BankReviewItem[]): void {
    this.items.set(items);
    for (const item of items) {
      this.edits[item.id] ??= item.acceptedAnswers.join('\n');
    }
  }
}
