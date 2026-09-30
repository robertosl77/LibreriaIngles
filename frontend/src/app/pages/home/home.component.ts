import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ClassSummary } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { STATUS_LABELS, statusChip } from '../../shared/status';

@Component({
  selector: 'app-home',
  imports: [RouterLink, DatePipe],
  template: `
    <main class="page stack">
      <div class="page-header">
        <div>
          <p class="muted small">Hola{{ name() ? ', ' + name() : '' }}</p>
          <h1>Tu práctica de hoy</h1>
        </div>
        <button
          class="btn btn-primary"
          type="button"
          (click)="newClass()"
          [disabled]="creating() || (auth.me()?.ai?.connections ?? 0) === 0"
        >
          @if (creating()) {
            <span class="spinner"></span> Generando clase…
          } @else {
            Nueva clase
          }
        </button>
      </div>

      @if ((auth.me()?.ai?.connections ?? 0) === 0) {
        <div class="banner">
          Para generar clases necesitás al menos una conexión de IA.
          <a routerLink="/app/ia">Configurar conexiones</a>
        </div>
      } @else if ((auth.me()?.ai?.available ?? 0) === 0) {
        <div class="banner banner-bad">
          No hay conexiones de IA disponibles en este momento. Tu trabajo queda guardado y la
          corrección se reintenta sola. <a routerLink="/app/ia">Ver conexiones</a>
        </div>
      }

      @if (creating()) {
        <p class="banner banner-info small">
          La IA está armando una clase única para vos según tu nivel y tus puntos débiles. Puede
          tardar unos segundos.
        </p>
      }

      <section class="grid">
        <div class="card">
          <p class="muted small">Nivel operativo</p>
          <p class="big-number">{{ auth.me()?.studyProfile?.operationalLevel ?? '—' }}</p>
          <a class="small" routerLink="/app/nivel">Cambiar nivel</a>
        </div>
        <div class="card">
          <p class="muted small">Progreso general</p>
          <p class="big-number">{{ overall() === null ? '—' : overall() + '%' }}</p>
          <a class="small" routerLink="/app/progreso">Ver dashboard</a>
        </div>
        <div class="card">
          <p class="muted small">Clases completadas</p>
          <p class="big-number">{{ auth.me()?.classes?.completed ?? 0 }}</p>
          <a class="small" routerLink="/app/historial">Ver historial</a>
        </div>
        <div class="card">
          <p class="muted small">IA</p>
          <p class="big-number">{{ auth.me()?.ai?.available ?? 0 }}/{{ auth.me()?.ai?.connections ?? 0 }}</p>
          <a class="small" routerLink="/app/ia">Conexiones disponibles</a>
        </div>
      </section>

      @if (pending().length) {
        <section class="card">
          <h2>Pendientes</h2>
          <ul class="list">
            @for (item of pending(); track item.id) {
              <li class="list-item">
                <div>
                  <a [routerLink]="['/app/clase', item.id]"><strong>{{ item.title || 'Clase ' + item.id }}</strong></a>
                  <div class="muted small">
                    {{ item.targetLevel }} · {{ item.createdAt | date: 'dd/MM HH:mm' }}
                    @if (item.status === 'IN_PROGRESS' && item.total) {
                      · {{ item.answered }}/{{ item.total }} respondidos
                    }
                  </div>
                </div>
                <span [class]="statusChip(item.status)">{{ labels[item.status] }}</span>
              </li>
            }
          </ul>
        </section>
      }

      <section class="card">
        <h2>Últimas clases</h2>
        @if (loading()) {
          <p class="muted"><span class="spinner"></span></p>
        } @else if (recent().length === 0) {
          <p class="muted">Todavía no hiciste ninguna clase. Tocá <strong>Nueva clase</strong> para empezar.</p>
        } @else {
          <ul class="list">
            @for (item of recent(); track item.id) {
              <li class="list-item">
                <div>
                  <a [routerLink]="['/app/clase', item.id]"><strong>{{ item.title || 'Clase ' + item.id }}</strong></a>
                  <div class="muted small">{{ item.targetLevel }} · {{ item.createdAt | date: 'dd/MM HH:mm' }}</div>
                </div>
                <strong>{{ item.score === null ? '' : item.score + '%' }}</strong>
              </li>
            }
          </ul>
        }
      </section>
    </main>
  `
})
export class HomeComponent implements OnInit {
  readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);

  readonly labels = STATUS_LABELS;
  readonly statusChip = statusChip;
  readonly classes = signal<ClassSummary[]>([]);
  readonly loading = signal(true);
  readonly creating = signal(false);
  readonly overall = signal<number | null>(null);
  readonly name = computed(() => this.auth.me()?.account.displayName?.split(' ')[0] ?? '');
  readonly pending = computed(() => this.classes().filter((c) => c.status !== 'COMPLETED'));
  readonly recent = computed(() => this.classes().filter((c) => c.status === 'COMPLETED').slice(0, 5));

  async ngOnInit(): Promise<void> {
    try {
      const me = await this.auth.refreshMe();
      // Documento funcional §27.2: al volver a entrar, reintentar correcciones pendientes.
      if (me.classes.awaitingEvaluation > 0 && me.ai.available > 0) {
        const result = await firstValueFrom(this.api.processPending());
        if (result.completed > 0) {
          this.toast.success(`Se corrigieron ${result.completed} clase(s) pendiente(s).`);
          await this.auth.refreshMe();
        }
      }
      const [classes, progress] = await Promise.all([
        firstValueFrom(this.api.classes()),
        firstValueFrom(this.api.progress())
      ]);
      this.classes.set(classes);
      this.overall.set(progress.overallScore);
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  async newClass(): Promise<void> {
    this.creating.set(true);
    try {
      const created = await firstValueFrom(this.api.createClass());
      if (created.notice) {
        this.toast.show(created.notice);
      }
      await this.router.navigate(['/app/clase', created.id]);
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo generar la clase.'));
    } finally {
      this.creating.set(false);
    }
  }
}
