import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import {
  AiUsageReport,
  AiUsageRow,
  AiUsageScope,
  AiUsageScopeKind
} from '../../core/models';

@Component({
  selector: 'app-consumption',
  imports: [CommonModule],
  template: `
    <main class="page">
      <header class="page-header">
        <div>
          <h1>Consumo</h1>
          <p class="muted">
            Uso real de IA por operación. Entrada = tokens enviados al modelo; salida = tokens
            generados por el modelo.
          </p>
        </div>

        @if (scopes().length > 1) {
          <label class="scope-picker">
            Vista
            <select [value]="selectedKey()" (change)="changeScope($event)">
              @for (scope of scopes(); track scopeKey(scope)) {
                <option [value]="scopeKey(scope)">{{ scope.label }}</option>
              }
            </select>
          </label>
        }
      </header>

      @if (loading()) {
        <div class="card">Cargando consumo…</div>
      } @else if (error()) {
        <div class="alert error">{{ error() }}</div>
      } @else if (report(); as data) {
        <section class="summary" aria-label="Resumen de consumo">
          <article class="card metric">
            <span class="muted">Ejecuciones</span>
            <strong>{{ data.summary.executions | number }}</strong>
          </article>
          <article class="card metric">
            <span class="muted">Llamadas IA</span>
            <strong>{{ data.summary.requests | number }}</strong>
          </article>
          <article class="card metric">
            <span class="muted">Llamadas medidas</span>
            <strong>{{ data.summary.measuredRequests | number }}</strong>
          </article>
          <article class="card metric">
            <span class="muted">Tokens entrada</span>
            <strong>{{ data.summary.inputTokens | number }}</strong>
          </article>
          <article class="card metric">
            <span class="muted">Tokens salida</span>
            <strong>{{ data.summary.outputTokens | number }}</strong>
          </article>
          <article class="card metric">
            <span class="muted">Tokens totales</span>
            <strong>{{ data.summary.totalTokens | number }}</strong>
          </article>
          <article class="card metric">
            <span class="muted">Intentos con error</span>
            <strong>{{ data.summary.errors | number }}</strong>
          </article>
        </section>

        <section class="card table-card">
          <div class="table-title">
            <div>
              <h2>Detalle</h2>
              <p class="muted small">
                Cada fila corresponde a un intento real contra un proveedor. Los intentos de una
                misma ejecución comparten identificador. Sin precios ni costos en esta etapa.
              </p>
            </div>
            <span class="muted small">{{ data.total | number }} registros</span>
          </div>

          @if (data.rows.length === 0) {
            <p class="empty">Todavía no hay consumo registrado para esta vista.</p>
          } @else {
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Usuario</th>
                    <th>Operación</th>
                    <th>Ejecución</th>
                    <th>Referencia</th>
                    <th>Proveedor / modelo</th>
                    <th>Origen</th>
                    <th class="number">Entrada</th>
                    <th class="number">Salida</th>
                    <th class="number">Total</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of data.rows; track row.id) {
                    <tr>
                      <td class="nowrap">{{ row.createdAt | date:'dd/MM/yyyy HH:mm:ss' }}</td>
                      <td>
                        <div>{{ row.accountName || row.accountEmail || '—' }}</div>
                        @if (row.accountName && row.accountEmail) {
                          <div class="muted tiny">{{ row.accountEmail }}</div>
                        }
                      </td>
                      <td>{{ operationLabel(row.operation, row) }}</td>
                      <td>
                        @if (row.execution; as execution) {
                          <div class="nowrap">
                            <strong>#{{ execution.id.slice(0, 8) }}</strong>
                            <span class="muted tiny"> · intento {{ execution.attempt }}/{{ execution.attempts }}</span>
                          </div>
                          <span
                            class="execution-status"
                            [class.recovered]="execution.status === 'RECOVERED_BY_FAILOVER'"
                            [class.interrupted]="execution.status === 'INTERRUPTED'"
                          >
                            {{ executionStatusLabel(execution.status) }}
                          </span>
                        } @else {
                          <span class="muted">—</span>
                        }
                      </td>
                      <td>
                        @if (row.subject?.route) {
                          <a [href]="row.subject!.route!" target="_blank" rel="noopener">
                            {{ row.subject?.label || subjectFallback(row) }}
                          </a>
                        } @else {
                          {{ row.subject?.label || subjectFallback(row) }}
                        }
                      </td>
                      <td>
                        <div>{{ row.provider }}</div>
                        <div class="muted tiny">
                          {{ row.model || row.connectionName || '—' }}
                        </div>
                      </td>
                      <td>{{ sourceLabel(row) }}</td>
                      <td class="number">{{ tokenValue(row.inputTokens) }}</td>
                      <td class="number">{{ tokenValue(row.outputTokens) }}</td>
                      <td class="number total">{{ tokenValue(row.totalTokens) }}</td>
                      <td>
                        <span class="status" [class.ok]="row.success" [class.fail]="!row.success">
                          {{ row.success ? 'OK' : (row.errorCode || 'Error') }}
                        </span>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </section>
      }
    </main>
  `,
  styles: `
    .page {
      max-width: 1240px;
      margin: 0 auto;
      padding: 1.4rem 1rem 3rem;
    }
    .page-header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 1rem;
      margin-bottom: 1rem;
    }
    h1, h2 { margin: 0; }
    .page-header p { margin: 0.35rem 0 0; }
    .scope-picker {
      display: grid;
      gap: 0.3rem;
      min-width: 220px;
      font-size: 0.85rem;
      font-weight: 650;
    }
    .scope-picker select {
      min-height: 2.3rem;
      border: 1px solid var(--border);
      border-radius: 0.55rem;
      background: var(--surface);
      color: var(--text);
      padding: 0.4rem 0.55rem;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(7, minmax(120px, 1fr));
      gap: 0.7rem;
      margin-bottom: 1rem;
    }
    .metric {
      display: grid;
      gap: 0.3rem;
    }
    .metric strong {
      font-size: 1.35rem;
    }
    .table-card { padding: 0; overflow: hidden; }
    .table-title {
      padding: 1rem;
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: start;
      border-bottom: 1px solid var(--border);
    }
    .table-title p { margin: 0.3rem 0 0; }
    .table-wrap { overflow: auto; }
    table {
      width: 100%;
      min-width: 1240px;
      border-collapse: collapse;
      font-size: 0.88rem;
    }
    th, td {
      text-align: left;
      padding: 0.72rem 0.75rem;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      background: var(--surface);
      font-size: 0.78rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    tr:last-child td { border-bottom: 0; }
    .number { text-align: right; font-variant-numeric: tabular-nums; }
    .total { font-weight: 700; }
    .nowrap { white-space: nowrap; }
    .tiny { font-size: 0.76rem; }
    .small { font-size: 0.85rem; }
    .muted { color: var(--muted); }
    .empty { padding: 1rem; margin: 0; }
    .execution-status {
      display: inline-block;
      margin-top: 0.2rem;
      border-radius: 999px;
      padding: 0.1rem 0.42rem;
      font-size: 0.7rem;
      font-weight: 700;
      background: var(--success-bg, #e8f5e9);
      white-space: nowrap;
    }
    .execution-status.recovered { background: var(--warning-bg, #fff4dc); }
    .execution-status.interrupted { background: var(--danger-bg, #fdecec); }
    .status {
      display: inline-block;
      border-radius: 999px;
      padding: 0.12rem 0.45rem;
      font-size: 0.75rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .status.ok { background: var(--success-bg, #e8f5e9); }
    .status.fail { background: var(--danger-bg, #fdecec); }
    .alert.error {
      padding: 0.9rem 1rem;
      border-radius: 0.6rem;
      background: var(--danger-bg, #fdecec);
    }
    @media (max-width: 900px) {
      .summary { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 640px) {
      .page-header { align-items: stretch; flex-direction: column; }
      .summary { grid-template-columns: repeat(2, 1fr); }
      .scope-picker { min-width: 0; }
    }
  `
})
export class ConsumptionComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly scopes = signal<AiUsageScope[]>([]);
  readonly selectedKey = signal('ME');
  readonly report = signal<AiUsageReport | null>(null);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    try {
      const scopes = await firstValueFrom(this.api.aiUsageScopes());
      const available = scopes ?? [];
      this.scopes.set(available);
      const preferred =
        available.find((item) => item.kind === 'PLATFORM') ??
        available.find((item) => item.kind === 'ORGANIZATION') ??
        available[0];
      if (preferred) {
        this.selectedKey.set(this.scopeKey(preferred));
        await this.load(preferred);
      } else {
        this.loading.set(false);
      }
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo cargar el consumo.'));
      this.loading.set(false);
    }
  }

  scopeKey(scope: AiUsageScope): string {
    return `${scope.kind}:${scope.id ?? ''}`;
  }

  async changeScope(event: Event): Promise<void> {
    const key = (event.target as HTMLSelectElement).value;
    const scope = this.scopes().find((item) => this.scopeKey(item) === key);
    if (!scope) return;
    this.selectedKey.set(key);
    await this.load(scope);
  }

  operationLabel(operation: string, row: AiUsageRow): string {
    const labels: Record<string, string> = {
      generate_class: row.subject?.type === 'EXAM' ? 'Generar examen' : 'Generar clase',
      evaluate_answer: 'Corregir ejercicio',
      transcribe_audio: 'Transcribir / analizar audio',
      campaign_assist: 'Asistente de campaña'
    };
    return labels[operation] ?? operation.replaceAll('_', ' ');
  }

  executionStatusLabel(status: 'OK' | 'RECOVERED_BY_FAILOVER' | 'INTERRUPTED'): string {
    if (status === 'RECOVERED_BY_FAILOVER') return 'Recuperada por failover';
    if (status === 'INTERRUPTED') return 'Interrumpida';
    return 'OK';
  }

  sourceLabel(row: AiUsageRow): string {
    if (row.serviceSource === 'HYBRID') {
      return row.actualSource === 'PLATFORM' ? 'Híbrido → Plataforma' : 'Híbrido → propia';
    }
    if (row.actualSource === 'ORGANIZATION') return 'IA de organización';
    if (row.actualSource === 'PLATFORM') return 'IA de plataforma';
    return 'API propia';
  }

  subjectFallback(row: AiUsageRow): string {
    return row.subject?.type || '—';
  }

  tokenValue(value: number | null): string {
    return value === null ? '—' : value.toLocaleString('es-AR');
  }

  private async load(scope: AiUsageScope): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const data = await firstValueFrom(
        this.api.aiUsage(scope.kind as AiUsageScopeKind, scope.id, 200, 0)
      );
      this.report.set(data ?? null);
    } catch (err) {
      this.report.set(null);
      this.error.set(errorMessage(err, 'No se pudo cargar el consumo.'));
    } finally {
      this.loading.set(false);
    }
  }
}
