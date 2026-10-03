import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { PlatformOverview } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { AccountsSummaryComponent } from './accounts-summary.component';

@Component({
  selector: 'app-platform-overview',
  imports: [DatePipe, AccountsSummaryComponent],
  template: `
    <section class="stack overview">
      <div class="overview-toolbar">
        <span class="muted small">Actividad de las últimas 24 h y tendencia diaria.</span>
        <button class="btn btn-sm" type="button" (click)="load()" [disabled]="loading()">
          Actualizar
        </button>
      </div>

      @if (data(); as d) {
        <section class="grid">
          <div class="card metric-card">
            <p class="muted small">Requests de IA · 24 h</p>
            <p class="big-number">{{ d.last24h.all.requests }}</p>
            <p class="muted small">{{ d.last24h.all.errors }} con error</p>
          </div>
          <div class="card metric-card">
            <p class="muted small">De plataforma · 24 h</p>
            <p class="big-number">{{ d.last24h.platform.successful }}</p>
            <p class="muted small">exitosos (costo propio)</p>
          </div>
          <div class="card metric-card">
            <p class="muted small">Usuarios activos · 24 h</p>
            <p class="big-number">{{ d.last24h.activeAccounts }}</p>
            <p class="muted small">de {{ d.accounts }} cuentas</p>
          </div>
          <div class="card metric-card">
            <p class="muted small">Clases pedidas · 24 h</p>
            <p class="big-number">{{ d.last24h.classesCreated }}</p>
            <p class="muted small">incluye las que fallaron</p>
          </div>
        </section>

        <app-accounts-summary />

        <section class="card">
          <div class="chart-head">
            <div>
              <h2>Requests de IA por día</h2>
              <p class="muted small">Últimos {{ d.daily.length }} días · todas las conexiones</p>
            </div>
          </div>

          <div class="chart" role="img" [attr.aria-label]="chartLabel()">
            <div class="y-max muted small">{{ maxDaily() }}</div>
            <div class="bars">
              @for (day of d.daily; track day.date; let i = $index) {
                <div class="bar-slot" tabindex="0">
                  <div
                    class="col"
                    [style.height.%]="barHeight(day.requests)"
                    [class.empty]="day.requests === 0"
                  ></div>
                  <div class="tip">
                    <strong>{{ shortDate(day.date) }}</strong><br />
                    {{ day.requests }} requests<br />
                    {{ day.platform }} de plataforma · {{ day.errors }} con error
                  </div>
                  <span
                    class="x-label muted"
                    [class.hidden]="i % 2 !== 0 && i !== d.daily.length - 1"
                  >
                    {{ shortDate(day.date) }}
                  </span>
                </div>
              }
            </div>
          </div>

          <details class="table-view">
            <summary class="small">Ver como tabla</summary>
            <table>
              <thead>
                <tr>
                  <th>Día</th>
                  <th>Requests</th>
                  <th>De plataforma</th>
                  <th>Con error</th>
                </tr>
              </thead>
              <tbody>
                @for (day of d.daily; track day.date) {
                  <tr>
                    <td>{{ shortDate(day.date) }}</td>
                    <td>{{ day.requests }}</td>
                    <td>{{ day.platform }}</td>
                    <td>{{ day.errors }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </details>
        </section>

        @if (d.connections.length) {
          <section class="card">
            <h2>Consumo por conexión de plataforma</h2>
            <ul class="list">
              @for (c of d.connections; track c.id) {
                <li class="list-item">
                  <strong>{{ c.name }}</strong>
                  <span class="small">
                    24 h: <strong>{{ c.last24h.successful }}</strong> ok · {{ c.last24h.errors }} error
                    <span class="muted">
                      · 30 días: {{ c.last30d.successful }} ok · {{ c.last30d.errors }} error
                    </span>
                  </span>
                </li>
              }
            </ul>
          </section>
        }

        <section class="card">
          <h2>Cuentas que más usan IA de plataforma · 24 h</h2>
          @if (d.topAccounts24h.length === 0) {
            <p class="muted">Sin consumo de plataforma en las últimas 24 h.</p>
          } @else {
            <ul class="list">
              @for (a of d.topAccounts24h; track a.email) {
                <li class="list-item">
                  <span>{{ a.email }}</span>
                  <strong>{{ a.requests }}</strong>
                </li>
              }
            </ul>
          }
        </section>

        <section class="card">
          <h2>Uso de beneficios</h2>
          @if (d.benefitUsage.length === 0) {
            <p class="muted">Todavía no hay beneficios configurados.</p>
          } @else {
            <ul class="list">
              @for (benefit of d.benefitUsage; track benefit.id) {
                <li class="list-item benefit-usage-row">
                  <strong>{{ benefit.name }}</strong>
                  <span class="small muted">
                    {{ benefit.campaigns }} campaña(s) · {{ benefit.invitations }} invitación(es)
                  </span>
                </li>
              }
            </ul>
          }
        </section>


      } @else if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      }
    </section>
  `,
  styles: `
    .overview { gap: 1rem; }

    .overview-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      min-height: 2rem;
    }

    .metric-card {
      min-height: 7.2rem;
    }

    .chart-head h2,
    .chart-head p {
      margin: 0;
    }

    .chart-head p {
      margin-top: 0.2rem;
    }

    .chart { position: relative; padding-left: 2rem; }
    .y-max { position: absolute; left: 0; top: 0; }

    .bars {
      height: 160px;
      display: flex;
      align-items: flex-end;
      gap: 2px;
      border-bottom: 1px solid var(--border);
      background-image: linear-gradient(var(--border) 1px, transparent 1px);
      background-size: 100% 50%;
    }

    .bar-slot {
      position: relative;
      flex: 1;
      height: 100%;
      display: flex;
      align-items: flex-end;
      outline: none;
    }

    .col {
      width: 100%;
      background: var(--accent);
      border-radius: 4px 4px 0 0;
      min-height: 0;
    }

    .col.empty {
      height: 2px !important;
      background: var(--border);
      border-radius: 0;
    }

    .bar-slot:hover .col, .bar-slot:focus .col { opacity: 0.8; }

    .tip {
      display: none;
      position: absolute;
      bottom: calc(100% + 6px);
      left: 50%;
      transform: translateX(-50%);
      background: #161616;
      color: #fff;
      padding: 0.45rem 0.6rem;
      border-radius: 0.5rem;
      font-size: 0.78rem;
      white-space: nowrap;
      z-index: 5;
      pointer-events: none;
    }

    .bar-slot:hover .tip, .bar-slot:focus .tip { display: block; }
    .bar-slot:first-child .tip { left: 0; transform: none; }
    .bar-slot:last-child .tip { left: auto; right: 0; transform: none; }

    .x-label {
      position: absolute;
      top: calc(100% + 4px);
      left: 50%;
      transform: translateX(-50%);
      font-size: 0.7rem;
      white-space: nowrap;
    }

    .x-label.hidden { visibility: hidden; }
    .table-view { margin-top: 2rem; }

    .table-view table {
      border-collapse: collapse;
      margin-top: 0.6rem;
      font-size: 0.85rem;
    }

    .table-view th, .table-view td {
      text-align: left;
      padding: 0.3rem 1rem 0.3rem 0;
      border-bottom: 1px solid var(--border);
    }

    .benefit-usage-row {
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
    }

    .table-wrap { overflow-x: auto; }

    .account-benefits {
      width: 100%;
      border-collapse: collapse;
      margin-top: 0.6rem;
      font-size: 0.85rem;
    }

    .account-benefits th,
    .account-benefits td {
      text-align: left;
      padding: 0.4rem 0.9rem 0.4rem 0;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }

    @media (max-width: 560px) {
      .overview-toolbar {
        align-items: flex-start;
      }
    }
  `
})
export class PlatformOverviewComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly data = signal<PlatformOverview | null>(null);
  readonly loading = signal(true);
  readonly maxDaily = computed(() =>
    Math.max(1, ...(this.data()?.daily.map((d) => d.requests) ?? [0]))
  );
  readonly chartLabel = computed(() => {
    const daily = this.data()?.daily ?? [];
    const total = daily.reduce((sum, d) => sum + d.requests, 0);
    return `Requests de IA por día, últimos ${daily.length} días: ${total} en total.`;
  });

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      this.data.set(await firstValueFrom(this.api.platformOverview()));
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  barHeight(value: number): number {
    return (value / this.maxDaily()) * 100;
  }

  shortDate(iso: string): string {
    const [, month, day] = iso.split('-');
    return `${day}/${month}`;
  }

  originLabel(origin: PlatformOverview['accountBenefits'][number]['origin']): string {
    return {
      MANUAL: 'Manual',
      CAMPAIGN: 'Campaña',
      INVITATION: 'Invitación',
      PAYMENT: 'Pago'
    }[origin];
  }
}
