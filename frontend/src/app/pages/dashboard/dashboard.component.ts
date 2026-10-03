import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AbilityProgress, Dashboard, SkillProgress } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';
import { scoreChip } from '../../shared/status';

const SKILL_STATUS: Record<SkillProgress['status'], { label: string; chip: string }> = {
  NOT_STARTED: { label: 'Sin practicar', chip: 'chip' },
  LEARNING: { label: 'Aprendiendo', chip: 'chip chip-warn' },
  MASTERED: { label: 'Dominado', chip: 'chip chip-ok' },
  NEEDS_REVIEW: { label: 'Repasar', chip: 'chip chip-bad' }
};

const CONFIDENCE: Record<string, string> = { low: 'baja', medium: 'media', high: 'alta' };
const TREND: Record<string, string> = { up: '↑ mejorando', down: '↓ bajando', stable: '→ estable' };

/** Qué suma a cada habilidad (T-034): un ejercicio deja evidencia en varias. */
const ABILITY_HELP: Record<AbilityProgress['key'], string> = {
  GRAMMAR: 'Ejercicios de gramática, leídos o escuchados, escritos o hablados.',
  VOCABULARY: 'Ejercicios de vocabulario, leídos o escuchados, escritos o hablados.',
  LISTENING:
    'Todo lo que respondiste escuchando, sea del tema que sea. Escuchar varias veces o en lento descuenta: entendiste, pero te costó.',
  SPEAKING: 'Lo que respondiste hablando: cuenta lo que dijiste, no cómo sonó.',
  PRONUNCIATION:
    'Cómo sonó lo que dijiste (estimación de la IA). Si una palabra sonó como otra (think → sink), queda limitada.',
  READING: 'Textos que leíste. Un texto escuchado cuenta como Listening, no como Reading.',
  WRITING: 'Ejercicios de escritura, donde armás la oración vos. Reescribir una oración dada cuenta como Grammar.'
};

@Component({
  selector: 'app-dashboard',
  imports: [RouterLink, CollapseCardComponent],
  template: `
    <main class="page stack">
      <div class="page-header">
        <div>
          <h1>Progreso</h1>
          <p class="muted">Cómo vas en cada habilidad del idioma. Tocá una para ver el detalle.</p>
        </div>
      </div>

      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      }
      @if (!loading() && data(); as d) {
        <section class="grid">
          <div class="card">
            <p class="muted small">Nivel</p>
            <p class="big-number">{{ d.level }}</p>
          </div>
          <div class="card">
            <p class="muted small">Promedio de lo practicado</p>
            <p class="big-number">{{ d.overallScore === null ? '—' : d.overallScore + '%' }}</p>
          </div>
          <div class="card">
            <p class="muted small">Temas practicados</p>
            <p class="big-number">{{ d.skillsPracticed }}/{{ d.skillsTotal }}</p>
          </div>
        </section>

        @if (d.orthography; as orthography) {
          <section class="card orthography-card">
            <div>
              <p class="muted small">Convenciones de escritura</p>
              <h2>Ortografía</h2>
              <p class="muted small">
                Mayúsculas, spelling, puntuación y apóstrofes. Vive dentro de Writing,
                pero se sigue por separado.
              </p>
            </div>
            <div class="orthography-score">
              <strong>{{ orthography.score === null ? '—' : orthography.score + '%' }}</strong>
              <span [class]="statusInfo(orthography.status).chip">{{ statusInfo(orthography.status).label }}</span>
              <span class="muted small">
                {{ orthography.skillsPracticed }}/{{ orthography.skillsTotal }} tema(s) practicados
              </span>
            </div>
          </section>
        }

        @if (d.weakest.length) {
          <section class="card">
            <h2>Para reforzar</h2>
            <p class="muted small">Las próximas clases van a darle más peso a estos temas.</p>
            <div class="row weak">
              @for (w of d.weakest; track w.key) {
                <span [class]="scoreChip(w.score)">{{ w.name }} · {{ w.score }}%</span>
              }
            </div>
          </section>
        }

        @if (d.skillsPracticed === 0) {
          <p class="banner banner-info">
            Todavía no hay datos. Hacé tu primera clase desde el <a routerLink="/app">inicio</a>.
          </p>
        }

        <section class="abilities" aria-label="Habilidades">
          @for (ab of d.abilities; track ab.key) {
            @let area = areaOf(d, ab);
            <app-collapse-card>
              <div collapse-header class="ability-head" [class.empty]="ab.score === null">
                <span class="ab-name">{{ ab.name }}</span>
                <span class="ab-chip" [class]="statusInfo(ab.status).chip">{{ statusInfo(ab.status).label }}</span>
                <strong class="ab-score">{{ ab.score === null ? '—' : ab.score + '%' }}</strong>
                <span class="bar ab-bar"><span [class]="'ab-fill ' + band(ab.score)" [style.width.%]="ab.score ?? 0"></span></span>
                <span class="muted small ab-meta">
                  {{ ab.evidenceCount }} evidencia(s)
                  @if (ab.trend) { · {{ trend[ab.trend] }} }
                  @if (ab.assistedRecent) { · <span class="help-mark">{{ ab.assistedRecent }} reciente(s) con ayuda</span> }
                </span>
              </div>

              <div class="ab-body">
                <p class="muted small">{{ help[ab.key] }}</p>

                @if (ab.score === null) {
                  <p class="small">Todavía no hiciste ejercicios que midan esta habilidad.</p>
                }

                @if (ab.assistedCount) {
                  <p class="small">
                    {{ ab.assistedCount }} de {{ ab.evidenceCount }} con ayuda (lección, escuchar de nuevo o practicar
                    varias veces). Cuentan menos, y con ayuda reciente no se da por dominada.
                  </p>
                }

                @if (ab.key === 'PRONUNCIATION' && ab.practiceTrials) {
                  <div class="practice">
                    <p class="label">Práctica antes de responder</p>
                    <p class="small">
                      {{ ab.practiceTrials }} práctica(s) · de <strong>{{ ab.practiceFirst }}%</strong>
                      a <strong>{{ ab.practiceLast }}%</strong>
                      @if (ab.practiceLast! > ab.practiceFirst!) { <span class="up">· mejoró</span> }
                    </p>
                    <p class="muted small">La práctica no cambia tu puntaje: muestra tu evolución.</p>
                  </div>
                }

                @if (showSources(ab.key) && ab.sources.length) {
                  <div class="sources">
                    <p class="label">De dónde vino</p>
                    <ul class="list">
                      @for (src of ab.sources; track src.skillKey) {
                        <li class="list-item skill">
                          <div class="skill-name">
                            <span>{{ src.name }}</span>
                            <span class="muted small">
                              {{ src.count }} ejercicio(s)
                              @if (src.assistedCount) { · <span class="help-mark">{{ src.assistedCount }} con ayuda</span> }
                            </span>
                          </div>
                          <strong>{{ src.score === null ? '' : src.score + '%' }}</strong>
                        </li>
                      }
                    </ul>
                  </div>
                }

                @if (area) {
                  @for (topic of area.topics; track topic.key) {
                    <div class="topic">
                      <div class="topic-head">
                        <strong>{{ topic.name }}</strong>
                        <span class="muted">{{ topic.score === null ? '—' : topic.score + '%' }}</span>
                      </div>
                      <ul class="list">
                        @for (skill of topic.skills; track skill.key) {
                          <li class="list-item skill">
                            <div class="skill-name">
                              <span>{{ skill.name }}</span>
                              <span class="muted small">
                                {{ skill.attemptCount }} intento(s) · confianza {{ confidence[skill.confidence] || skill.confidence }}
                                @if (skill.trend) { · {{ trend[skill.trend] }} }
                                @if (skill.assistedRecent) { · {{ skill.assistedRecent }} reciente(s) con lección }
                              </span>
                            </div>
                            <div class="skill-score">
                              <span [class]="statusInfo(skill.status).chip">{{ statusInfo(skill.status).label }}</span>
                              <strong>{{ skill.score === null ? '' : skill.score + '%' }}</strong>
                            </div>
                          </li>
                        }
                      </ul>
                    </div>
                  }
                }
              </div>
            </app-collapse-card>
          }
        </section>
      }
    </main>
  `,
  styles: `
    .orthography-card { display: flex; justify-content: space-between; gap: 1rem; align-items: center; }
    .orthography-card h2 { margin: 0.1rem 0 0.25rem; }
    .orthography-score { display: flex; flex-direction: column; align-items: flex-end; gap: 0.25rem; }
    .orthography-score > strong { font-size: 1.8rem; }
    .abilities { display: flex; flex-direction: column; gap: 0.7rem; }
    .ability-head {
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 0.3rem 0.8rem;
      align-items: center;
    }
    .ab-name { font-weight: 700; font-size: 1.05rem; min-width: 0; }
    .weak .chip { white-space: normal; }
    .ab-score { min-width: 3.5rem; text-align: right; }
    .ab-bar { grid-column: 1 / -1; margin: 0.2rem 0 0; }
    /* Color por tramo (0-25 rojo, 25-50 naranja, 50-75 azul, 75-100 verde), con degradé suave del mismo tono. */
    .ab-fill.b-red { background: linear-gradient(90deg, #e8857a, #c8382b); }
    .ab-fill.b-orange { background: linear-gradient(90deg, #f3b56b, #dd7a12); }
    .ab-fill.b-blue { background: linear-gradient(90deg, #7fa5ec, #2f5fc9); }
    .ab-fill.b-green { background: linear-gradient(90deg, #6fcf9b, #1f8a52); }
    .ab-meta { grid-column: 1 / -1; }
    .help-mark { color: var(--warn); font-weight: 600; }
    .ability-head.empty .ab-name { color: var(--muted); }
    .ab-body { display: flex; flex-direction: column; gap: 0.5rem; }
    .ab-body p { margin: 0; }
    .practice { background: var(--info-bg); border-radius: 0.6rem; padding: 0.6rem 0.8rem; display: flex; flex-direction: column; gap: 0.2rem; }
    .label { font-weight: 600; font-size: 0.85rem; }
    .sources { margin-top: 0.4rem; }
    .up { color: var(--ok); font-weight: 600; }
    .topic { margin-top: 0.6rem; }
    .topic-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
    .skill-name { display: flex; flex-direction: column; gap: 0.15rem; }
    .skill-score { display: flex; gap: 0.6rem; align-items: center; min-width: 150px; justify-content: flex-end; }
    @media (max-width: 560px) {
      .orthography-card { align-items: flex-start; flex-direction: column; }
      .orthography-score { align-items: flex-start; }
      .ability-head { gap: 0.3rem 0.45rem; grid-template-columns: 1fr auto; }
      .ab-score { min-width: 0; }
      .ab-chip { grid-row: 2; grid-column: 1 / -1; justify-self: start; }
      .skill { flex-direction: column; align-items: flex-start; }
      .skill-score { justify-content: flex-start; min-width: 0; }
    }
  `
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly status = SKILL_STATUS;
  readonly confidence = CONFIDENCE;
  readonly trend = TREND;
  readonly help = ABILITY_HELP;
  readonly scoreChip = scoreChip;
  readonly data = signal<Dashboard | null>(null);
  readonly loading = signal(true);

  statusInfo(status: SkillProgress['status']): { label: string; chip: string } {
    return this.status[status] ?? this.status.NOT_STARTED;
  }

  /** Habilidades transversales: se alimentan de ejercicios de cualquier tema. */
  showSources(key: AbilityProgress['key']): boolean {
    return key === 'LISTENING' || key === 'SPEAKING' || key === 'PRONUNCIATION';
  }

  /** Tramo de color de la barra según el puntaje. */
  band(score: number | null): string {
    const v = score ?? 0;
    return v < 25 ? 'b-red' : v < 50 ? 'b-orange' : v < 75 ? 'b-blue' : 'b-green';
  }

  /** Los temas del currículum viven dentro de la habilidad de su área. */
  areaOf(d: Dashboard, ability: AbilityProgress): Dashboard['areas'][number] | undefined {
    return d.areas.find((a) => a.key.toUpperCase() === ability.key);
  }

  async ngOnInit(): Promise<void> {
    try {
      this.data.set(await firstValueFrom(this.api.progress()));
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }
}
