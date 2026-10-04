import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import {
  AiUsageDiagnosticResponse,
  AiUsageReference,
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
            Uso real de IA por operación. Entrada = tokens enviados al modelo; pensamiento = tokens
            internos de razonamiento cuando el proveedor los informa; salida = tokens generados.
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
            <span class="muted">Pensamiento</span>
            <strong>{{ data.summary.reasoningTokens | number }}</strong>
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
                    @if (data.scope !== 'ME') {
                      <th>Usuario</th>
                    }
                    <th>Operación</th>
                    <th>Ejecución</th>
                    <th>Referencia</th>
                    <th>Proveedor / modelo</th>
                    <th>Origen</th>
                    <th class="number">Entrada</th>
                    <th class="number">Pensamiento</th>
                    <th class="number">Salida</th>
                    <th class="number">Total</th>
                    <th>Diagnóstico</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  @for (row of data.rows; track row.id) {
                    <tr>
                      <td class="nowrap">{{ row.createdAt | date:'dd/MM/yyyy HH:mm:ss' }}</td>
                      @if (data.scope !== 'ME') {
                        <td>
                          <div>{{ row.accountName || row.accountEmail || '—' }}</div>
                          @if (row.accountName && row.accountEmail) {
                            <div class="muted tiny">{{ row.accountEmail }}</div>
                          }
                        </td>
                      }
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
                        @if (row.subject?.previewable) {
                          <button class="reference-link" type="button" (click)="openReference(row)">
                            {{ row.subject?.label || subjectFallback(row) }}
                          </button>
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
                      <td class="number">{{ tokenValue(row.reasoningTokens) }}</td>
                      <td class="number">{{ tokenValue(row.outputTokens) }}</td>
                      <td class="number total">{{ tokenValue(row.totalTokens) }}</td>
                      <td>
                        <button class="reference-link" type="button" (click)="openDiagnostic(row)">Analizar</button>
                      </td>
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

      @if (diagnosticLoading()) {
        <div class="modal-backdrop" (click)="closeDiagnostic()">
          <section class="reference-modal card" (click)="$event.stopPropagation()">
            <p>Cargando diagnóstico…</p>
          </section>
        </div>
      } @else if (diagnosticPreview(); as report) {
        <div class="modal-backdrop" (click)="closeDiagnostic()">
          <section class="reference-modal card" (click)="$event.stopPropagation()">
            <header class="modal-head">
              <div>
                <h2>Diagnóstico de consumo</h2>
                <p class="muted small">{{ operationName(report.operation) }} · evento #{{ report.eventId }}</p>
              </div>
              <button class="modal-close" type="button" (click)="closeDiagnostic()" aria-label="Cerrar">×</button>
            </header>

            <section class="execution-context">
              <h3>Qué consumió</h3>
              <div class="context-grid">
                <div><span>Entrada</span><strong>{{ tokenValue(report.diagnostic.tokens.input) }}</strong></div>
                <div><span>Pensamiento</span><strong>{{ tokenValue(report.diagnostic.tokens.reasoning) }}</strong></div>
                <div><span>Salida</span><strong>{{ tokenValue(report.diagnostic.tokens.output) }}</strong></div>
                <div><span>Total</span><strong>{{ tokenValue(report.diagnostic.tokens.total) }}</strong></div>
              </div>
            </section>

            @if (report.diagnostic.snapshot; as snapshot) {
              <section class="execution-context">
                <h3>Qué contexto participó</h3>
                <p class="muted tiny">Huella estructurada de la llamada real. No se guardan prompts ni respuestas completas.</p>
                <div class="context-grid">
                  @if (snapshot.systemChars !== undefined) {
                    <div><span>Prompt base</span><strong>{{ snapshot.systemChars | number }} caracteres</strong></div>
                  }
                  @if (snapshot.userChars !== undefined) {
                    <div><span>Contexto dinámico</span><strong>{{ snapshot.userChars | number }} caracteres</strong></div>
                  }
                  @if (snapshot.systemFingerprint) {
                    <div><span>Versión de prompt</span><strong>{{ snapshot.systemFingerprint }}</strong></div>
                  }
                  @if (snapshot.responseJsonChars !== undefined) {
                    <div><span>Respuesta estructurada</span><strong>{{ snapshot.responseJsonChars | number }} caracteres</strong></div>
                  }
                  @if (snapshot.audioBytes !== undefined) {
                    <div><span>Audio</span><strong>{{ snapshot.audioBytes | number }} bytes</strong></div>
                  }
                  @for (detail of diagnosticDetails(snapshot); track detail.key) {
                    <div><span>{{ detail.label }}</span><strong>{{ detail.value }}</strong></div>
                  }
                </div>
              </section>
            } @else {
              <p class="muted small">Este evento es anterior a la instrumentación diagnóstica.</p>
            }

            <section class="execution-context">
              <h3>Qué fue distinto</h3>
              @if (report.diagnostic.comparison.enoughSample) {
                <div class="context-grid">
                  <div><span>Muestra comparable</span><strong>{{ report.diagnostic.comparison.sampleSize }}</strong></div>
                  <div><span>Mediana total</span><strong>{{ tokenValue(report.diagnostic.comparison.medianTotalTokens) }}</strong></div>
                  <div><span>Percentil 90</span><strong>{{ tokenValue(report.diagnostic.comparison.p90TotalTokens) }}</strong></div>
                  <div>
                    <span>Esta llamada / mediana</span>
                    <strong>{{ ratioLabel(report.diagnostic.comparison.totalVsMedian) }}</strong>
                  </div>
                </div>
                @if (report.diagnostic.comparison.signals.length) {
                  <div class="diagnostic-signals">
                    <strong>Señales para revisar</strong>
                    @for (signal of report.diagnostic.comparison.signals; track signal.key) {
                      <div class="diagnostic-signal">
                        <span>{{ signal.label }}</span>
                        <strong>{{ diagnosticNumber(signal.value) }} vs mediana {{ diagnosticNumber(signal.median) }} · {{ ratioLabel(signal.ratio) }}</strong>
                      </div>
                    }
                  </div>
                } @else {
                  <p class="muted small">No aparece ninguna dimensión medida al menos 1,5× por encima de su mediana.</p>
                }
              } @else {
                <p class="muted small">
                  Todavía no hay suficientes operaciones equivalentes para una comparación confiable
                  (muestra actual: {{ report.diagnostic.comparison.sampleSize }}).
                </p>
              }
              <p class="muted tiny">{{ report.diagnostic.note }}</p>
            </section>

            <div class="modal-actions">
              <button type="button" (click)="closeDiagnostic()">Cerrar</button>
            </div>
          </section>
        </div>
      }

      @if (referenceLoading()) {
        <div class="modal-backdrop" (click)="closeReference()">
          <section class="reference-modal card" (click)="$event.stopPropagation()">
            <p>Cargando referencia…</p>
          </section>
        </div>
      } @else if (referencePreview(); as preview) {
        <div class="modal-backdrop" (click)="closeReference()">
          <section class="reference-modal card" (click)="$event.stopPropagation()">
            <header class="modal-head">
              <div>
                <h2>{{ preview.class.label }}</h2>
                @if (preview.class.title) {
                  <p class="muted small">{{ preview.class.title }}</p>
                }
              </div>
              <button class="modal-close" type="button" (click)="closeReference()" aria-label="Cerrar">×</button>
            </header>

            @if (preview.kind === 'EXERCISE' && preview.exercise; as exercise) {
              <div class="exercise-preview">
                <p class="eyebrow">
                  Ejercicio {{ exercise.number }}
                  @if (exercise.conversation?.turn) {
                    · Turno {{ exercise.conversation?.turn }}/{{ exercise.conversation?.total || '?' }}
                  }
                  · {{ exercise.type }}
                </p>
                @if (exercise.area) {
                  <p class="muted small">{{ exercise.area }}</p>
                }

                @if (exercise.executionContext; as context) {
                  <section class="execution-context">
                    <h3>Cómo se ejecutó</h3>
                    <div class="context-grid">
                      <div><span>Operación IA</span><strong>{{ operationName(context.operation) }}</strong></div>
                      <div><span>Presentación</span><strong>{{ presentationLabel(context.presentationMode) }}</strong></div>
                      <div><span>Respuesta</span><strong>{{ responseLabel(context.responseMode) }}</strong></div>
                      <div><span>Evaluación configurada</span><strong>{{ evaluationModeLabel(context.evaluationMode) }}</strong></div>
                      <div><span>Evaluación efectiva</span><strong>{{ evaluationSourceLabel(context.evaluationSource) }}</strong></div>
                      <div><span>Audio de respuesta</span><strong>{{ durationLabel(context.audioDurationMs) }}</strong></div>
                      <div><span>Escuchas</span><strong>{{ context.listenPlays }}</strong></div>
                      <div><span>Escuchas lentas</span><strong>{{ context.listenSlowPlays }}</strong></div>
                      <div><span>Regrabaciones</span><strong>{{ context.speakRetakes }}</strong></div>
                      <div>
                        <span>Prácticas pronunciación</span>
                        <strong>{{ context.pronunciationPracticeScores.length }}</strong>
                      </div>
                      <div><span>Evaluación fonética</span><strong>{{ context.pronunciationEvaluated ? 'Sí' : 'No' }}</strong></div>
                      <div><span>Ayuda utilizada</span><strong>{{ assistanceLabel(context.assistance) }}</strong></div>
                    </div>
                    @if (context.pronunciationPracticeScores.length) {
                      <p class="muted small">
                        Puntajes de práctica: {{ context.pronunciationPracticeScores.join(' · ') }}
                      </p>
                    }
                    <div class="context-size">
                      <strong>Contexto observable</strong>
                      <span class="muted tiny">Tamaño en caracteres; sirve para comparar, no equivale a tokens.</span>
                      <div class="context-size-values">
                        <span>Consigna {{ context.contextStats.instructionChars }}</span>
                        <span>Pregunta {{ context.contextStats.questionChars }}</span>
                        <span>Texto {{ context.contextStats.passageChars }}</span>
                        <span>Respuesta {{ context.contextStats.answerChars }}</span>
                        <span>Opciones {{ context.contextStats.options }}</span>
                        <span>Conceptos esperados {{ context.contextStats.expectedConcepts }}</span>
                      </div>
                    </div>
                  </section>
                }

                @if (exercise.instruction) {
                  <p><strong>Consigna:</strong> {{ exercise.instruction }}</p>
                }
                @if (exercise.passage) {
                  <div class="preview-box"><strong>Texto:</strong><br>{{ exercise.passage }}</div>
                }
                <div class="preview-box"><strong>Pregunta / contenido:</strong><br>{{ exercise.question }}</div>
                @if (exercise.answer) {
                  <div class="preview-box"><strong>Respuesta:</strong><br>{{ exercise.answer }}</div>
                }
                @if (exercise.score !== null || exercise.feedback) {
                  <div class="preview-result">
                    @if (exercise.score !== null) { <strong>Resultado: {{ exercise.score }}%</strong> }
                    @if (exercise.feedback) { <p>{{ exercise.feedback }}</p> }
                    @if (exercise.correctAnswer) {
                      <p><span class="muted">Respuesta correcta:</span> {{ exercise.correctAnswer }}</p>
                    }
                  </div>
                }
              </div>
            } @else if (preview.exercises; as exercises) {
              <p class="muted small">
                Vista resumida de la clase generada para analizar el contenido asociado al consumo.
              </p>
              @if (preview.generationSummary; as summary) {
                <section class="execution-context">
                  <h3>Composición generada</h3>
                  <div class="context-grid">
                    <div><span>Actividades visibles</span><strong>{{ summary.logicalExercises }}</strong></div>
                    <div><span>Filas internas</span><strong>{{ summary.storedExerciseRows }}</strong></div>
                    <div><span>Presentación</span><strong>{{ distributionLabel(summary.presentationModes, 'presentation') }}</strong></div>
                    <div><span>Respuesta</span><strong>{{ distributionLabel(summary.responseModes, 'response') }}</strong></div>
                  </div>
                  <div class="context-size">
                    <strong>Tipos de ejercicio</strong>
                    <span>{{ distributionLabel(summary.types, 'type') }}</span>
                  </div>
                </section>
              }
              <div class="class-preview-list">
                @for (exercise of exercises; track exercise.id) {
                  <article class="preview-box">
                    <strong>
                      Ejercicio {{ exercise.number }}
                      @if (exercise.conversation?.turn) {
                        · Turno {{ exercise.conversation?.turn }}/{{ exercise.conversation?.total || '?' }}
                      }
                      · {{ exercise.type }}
                    </strong>
                    <p class="muted tiny">
                      {{ presentationLabel(exercise.presentation || 'READ') }}
                      · {{ responseLabel(exercise.responseMode || 'WRITE') }}
                    </p>
                    @if (exercise.instruction) { <p>{{ exercise.instruction }}</p> }
                    <p>{{ exercise.question }}</p>
                    @if (exercise.answer) {
                      <p><span class="muted">Respuesta:</span> {{ exercise.answer }}</p>
                    }
                    @if (exercise.score !== null) {
                      <p><span class="muted">Resultado:</span> {{ exercise.score }}%</p>
                    }
                  </article>
                }
              </div>
            }

            <footer class="modal-actions">
              @if (referenceCanReturnToExercise()) {
                <button type="button" (click)="showExerciseInModal()">
                  Volver al ejercicio
                </button>
              } @else if (preview.kind === 'EXERCISE') {
                <button class="open-class" type="button" (click)="showFullClassInModal()">
                  Ver clase completa
                </button>
              }
              @if (preview.fullClassRoute) {
                <button class="open-class" type="button" (click)="openFullClass(preview.fullClassRoute)">
                  Abrir clase en la aplicación
                </button>
              }
              <button type="button" (click)="closeReference()">Cerrar</button>
            </footer>
          </section>
        </div>
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
      grid-template-columns: repeat(8, minmax(115px, 1fr));
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
      min-width: 1340px;
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
    .reference-link {
      border: 0;
      padding: 0;
      background: transparent;
      color: inherit;
      text-decoration: underline;
      cursor: pointer;
      font: inherit;
      text-align: left;
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      z-index: 1000;
      background: rgb(0 0 0 / 0.42);
      display: grid;
      place-items: center;
      padding: 1rem;
    }
    .reference-modal {
      width: min(860px, 96vw);
      max-height: 88vh;
      overflow: auto;
      padding: 1.15rem;
      box-shadow: 0 18px 55px rgb(0 0 0 / 0.25);
    }
    .modal-head {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 1rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.75rem;
      margin-bottom: 0.9rem;
    }
    .modal-head p { margin: 0.3rem 0 0; }
    .modal-close {
      border: 0;
      background: transparent;
      font-size: 1.7rem;
      line-height: 1;
      cursor: pointer;
    }
    .eyebrow { font-weight: 700; margin: 0 0 0.25rem; }
    .execution-context {
      margin: 0.8rem 0 1rem;
      padding: 0.8rem;
      border: 1px solid var(--border);
      border-radius: 0.6rem;
      background: var(--surface);
    }
    .execution-context h3 {
      margin: 0 0 0.65rem;
      font-size: 0.95rem;
    }
    .context-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.55rem;
    }
    .context-grid > div {
      display: grid;
      gap: 0.12rem;
      min-width: 0;
    }
    .context-grid span {
      color: var(--muted);
      font-size: 0.72rem;
    }
    .context-grid strong {
      font-size: 0.82rem;
      overflow-wrap: anywhere;
    }
    .context-size {
      display: grid;
      gap: 0.3rem;
      margin-top: 0.65rem;
      padding-top: 0.65rem;
      border-top: 1px dashed var(--border);
      font-size: 0.82rem;
    }
    .context-size-values {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem 0.7rem;
      color: var(--muted);
      font-size: 0.75rem;
    }
    .diagnostic-signals {
      display: grid;
      gap: 0.45rem;
      margin-top: 0.8rem;
      padding-top: 0.7rem;
      border-top: 1px dashed var(--border);
    }
    .diagnostic-signal {
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      font-size: 0.82rem;
    }
    .diagnostic-signal strong { text-align: right; }
    .preview-box, .preview-result {
      border: 1px solid var(--border);
      border-radius: 0.55rem;
      padding: 0.75rem;
      margin-top: 0.65rem;
      white-space: pre-wrap;
    }
    .preview-result { background: var(--surface); }
    .preview-result p, .preview-box p { margin: 0.35rem 0 0; }
    .class-preview-list { display: grid; gap: 0.55rem; }
    .modal-actions {
      position: sticky;
      bottom: -1.15rem;
      z-index: 2;
      display: flex;
      justify-content: flex-end;
      gap: 0.55rem;
      margin: 1rem -1.15rem -1.15rem;
      padding: 0.8rem 1.15rem 1.15rem;
      border-top: 1px solid var(--border);
      background: var(--surface);
    }
    .modal-actions button {
      min-height: 2.2rem;
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      background: var(--surface);
      padding: 0.35rem 0.75rem;
      cursor: pointer;
    }
    .modal-actions .open-class { font-weight: 700; }
    @media (max-width: 900px) {
      .summary { grid-template-columns: repeat(3, 1fr); }
    }
    @media (max-width: 640px) {
      .page-header { align-items: stretch; flex-direction: column; }
      .context-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
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
  readonly referencePreview = signal<AiUsageReference | null>(null);
  readonly diagnosticPreview = signal<AiUsageDiagnosticResponse | null>(null);
  readonly diagnosticLoading = signal(false);
  readonly referenceLoading = signal(false);
  readonly referenceEventId = signal<number | null>(null);
  readonly referenceCanReturnToExercise = signal(false);

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

  async openDiagnostic(row: AiUsageRow): Promise<void> {
    this.diagnosticLoading.set(true);
    this.diagnosticPreview.set(null);
    try {
      this.diagnosticPreview.set(await firstValueFrom(this.api.aiUsageDiagnostic(row.id)));
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo abrir el diagnóstico.'));
    } finally {
      this.diagnosticLoading.set(false);
    }
  }

  closeDiagnostic(): void {
    this.diagnosticPreview.set(null);
    this.diagnosticLoading.set(false);
  }

  async openReference(row: AiUsageRow): Promise<void> {
    if (!row.subject?.previewable) return;
    this.referenceLoading.set(true);
    this.referencePreview.set(null);
    this.referenceEventId.set(row.id);
    this.referenceCanReturnToExercise.set(false);
    try {
      this.referencePreview.set(await firstValueFrom(this.api.aiUsageReference(row.id)));
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo abrir la referencia.'));
    } finally {
      this.referenceLoading.set(false);
    }
  }

  async showFullClassInModal(): Promise<void> {
    const eventId = this.referenceEventId();
    if (eventId === null) return;
    this.referenceLoading.set(true);
    try {
      this.referencePreview.set(
        await firstValueFrom(this.api.aiUsageReference(eventId, 'CLASS'))
      );
      this.referenceCanReturnToExercise.set(true);
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo abrir la clase completa.'));
    } finally {
      this.referenceLoading.set(false);
    }
  }

  async showExerciseInModal(): Promise<void> {
    const eventId = this.referenceEventId();
    if (eventId === null) return;
    this.referenceLoading.set(true);
    try {
      this.referencePreview.set(
        await firstValueFrom(this.api.aiUsageReference(eventId, 'REFERENCE'))
      );
      this.referenceCanReturnToExercise.set(false);
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo volver al ejercicio.'));
    } finally {
      this.referenceLoading.set(false);
    }
  }

  closeReference(): void {
    this.referencePreview.set(null);
    this.referenceLoading.set(false);
    this.referenceEventId.set(null);
    this.referenceCanReturnToExercise.set(false);
  }

  openFullClass(route: string): void {
    window.open(route, '_blank', 'noopener');
  }

  diagnosticDetails(snapshot: AiUsageDiagnosticResponse['diagnostic']['snapshot']): { key: string; label: string; value: string }[] {
    if (!snapshot?.details) return [];
    const labels: Record<string, string> = {
      exerciseType: 'Tipo de ejercicio',
      presentationMode: 'Presentación',
      responseMode: 'Respuesta',
      instructionChars: 'Consigna',
      questionChars: 'Pregunta',
      passageChars: 'Texto / pasaje',
      stimulusChars: 'Estímulo de escucha',
      answerChars: 'Respuesta del alumno',
      optionCount: 'Cantidad de opciones',
      optionsChars: 'Tamaño de opciones',
      referenceAnswerCount: 'Respuestas de referencia',
      referenceAnswersChars: 'Tamaño de referencias',
      objectiveCount: 'Objetivos curriculares',
      objectivesChars: 'Tamaño de objetivos',
      expectedConceptCount: 'Conceptos esperados',
      secondarySkillCount: 'Skills secundarios',
      conversationTurns: 'Turnos de conversación',
      conversationChars: 'Tamaño del historial',
      slotCount: 'Slots solicitados',
      conversationSlots: 'Slots conversacionales',
      typeCounts: 'Tipos solicitados',
      presentationCounts: 'Presentaciones solicitadas',
      responseCounts: 'Respuestas solicitadas',
      descriptionChars: 'Descripción del asistente',
      benefitCount: 'Beneficios disponibles',
      capabilityCount: 'Capacidades disponibles'
    };
    return Object.entries(snapshot.details).map(([key, value]) => ({
      key,
      label: labels[key] ?? key,
      value: this.diagnosticDetailValue(value, key.endsWith('Chars'))
    }));
  }

  diagnosticDetailValue(value: unknown, chars = false): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'object') {
      return Object.entries(value as Record<string, unknown>)
        .map(([key, item]) => `${key}: ${String(item)}`)
        .join(' · ') || '—';
    }
    if (typeof value === 'number') {
      return `${value.toLocaleString('es-AR')}${chars ? ' caracteres' : ''}`;
    }
    return String(value);
  }

  diagnosticNumber(value: number): string {
    return value.toLocaleString('es-AR', { maximumFractionDigits: 1 });
  }

  ratioLabel(value: number | null): string {
    return value === null ? '—' : `${value.toLocaleString('es-AR', { maximumFractionDigits: 2 })}×`;
  }

  operationName(operation: string): string {
    const labels: Record<string, string> = {
      generate_class: 'Generación de clase',
      evaluate_answer: 'Corrección de ejercicio',
      transcribe_audio: 'Transcripción / análisis de audio',
      campaign_assist: 'Asistente de campaña'
    };
    return labels[operation] ?? operation.replaceAll('_', ' ');
  }

  presentationLabel(mode: string): string {
    return mode === 'LISTEN' ? 'Escuchada' : mode === 'READ' ? 'Leída / visual' : mode;
  }

  responseLabel(mode: string): string {
    if (mode === 'SPEAK') return 'Hablada';
    if (mode === 'SELECT') return 'Selección';
    if (mode === 'WRITE') return 'Escrita';
    return mode;
  }

  evaluationModeLabel(mode: string): string {
    if (mode === 'AI') return 'IA';
    if (mode === 'HYBRID') return 'Híbrida';
    if (mode === 'DETERMINISTIC') return 'Reglas';
    return mode;
  }

  evaluationSourceLabel(source: string | null): string {
    if (!source) return 'Todavía sin resultado';
    if (source === 'AI') return 'IA';
    if (source === 'RULE_MATCH') return 'Regla determinística';
    if (source === 'COMMON_ERROR_MATCH') return 'Error conocido';
    return source;
  }

  assistanceLabel(value: string): string {
    if (value === 'LESSON') return 'Lección';
    if (value === 'HINT') return 'Pista';
    return 'Ninguna';
  }

  durationLabel(milliseconds: number | null): string {
    if (milliseconds === null) return '—';
    return `${(milliseconds / 1000).toLocaleString('es-AR', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    })} s`;
  }

  distributionLabel(
    values: Record<string, number>,
    kind: 'presentation' | 'response' | 'type'
  ): string {
    const items = Object.entries(values);
    if (!items.length) return '—';
    return items
      .map(([key, count]) => {
        const label =
          kind === 'presentation'
            ? this.presentationLabel(key)
            : kind === 'response'
              ? this.responseLabel(key)
              : key;
        return `${label}: ${count}`;
      })
      .join(' · ');
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
