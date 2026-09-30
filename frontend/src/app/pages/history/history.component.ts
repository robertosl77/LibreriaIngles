import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { ClassSummary } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { STATUS_LABELS, scoreChip, statusChip } from '../../shared/status';

@Component({
  selector: 'app-history',
  imports: [RouterLink, DatePipe],
  styles: `.chip-exam { margin-left: 0.4rem; background: #fbf3dc; color: #8a6a1f; }`,
  template: `
    <main class="page stack">
      <div class="page-header">
        <div>
          <h1>Historial</h1>
          <p class="muted">Todas tus clases. Podés abrir cualquiera para ver la corrección o rehacerla.</p>
        </div>
      </div>

      <section class="card">
        @if (loading()) {
          <p class="muted"><span class="spinner"></span></p>
        } @else if (classes().length === 0) {
          <p class="muted">Todavía no hay clases.</p>
        } @else {
          <ul class="list">
            @for (item of classes(); track item.id) {
              <li class="list-item">
                <div>
                  <a [routerLink]="['/app/clase', item.id]"><strong>{{ item.title || 'Clase ' + item.id }}</strong></a>
                  @if (item.kind === 'EXAM') { <span class="chip chip-exam">Examen</span> }
                  <div class="muted small">
                    #{{ item.id }} · {{ item.targetLevel }} · {{ item.createdAt | date: 'dd/MM/yyyy HH:mm' }}
                    @if (item.currentAttempt > 1) { · intento {{ item.currentAttempt }} }
                  </div>
                </div>
                <div class="row">
                  <span [class]="statusChip(item.status)">{{ labels[item.status] }}</span>
                  @if (item.score !== null) {
                    <span [class]="scoreChip(item.score)">{{ item.score }}%</span>
                  }
                </div>
              </li>
            }
          </ul>
        }
      </section>
    </main>
  `
})
export class HistoryComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly labels = STATUS_LABELS;
  readonly statusChip = statusChip;
  readonly scoreChip = scoreChip;
  readonly classes = signal<ClassSummary[]>([]);
  readonly loading = signal(true);

  async ngOnInit(): Promise<void> {
    try {
      this.classes.set(await firstValueFrom(this.api.classes()));
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }
}
