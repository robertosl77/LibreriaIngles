import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { Dashboard, SkillProgress } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { scoreChip } from '../../shared/status';

const SKILL_STATUS: Record<SkillProgress['status'], { label: string; chip: string }> = {
  NOT_STARTED: { label: 'Sin practicar', chip: 'chip' },
  LEARNING: { label: 'Aprendiendo', chip: 'chip chip-warn' },
  MASTERED: { label: 'Dominado', chip: 'chip chip-ok' },
  NEEDS_REVIEW: { label: 'Repasar', chip: 'chip chip-bad' }
};

const CONFIDENCE: Record<string, string> = { low: 'baja', medium: 'media', high: 'alta' };
const TREND: Record<string, string> = { up: '↑', down: '↓', stable: '→' };

@Component({
  selector: 'app-dashboard',
  imports: [RouterLink],
  template: `
    <main class="page stack">
      <div class="page-header">
        <div>
          <h1>Progreso</h1>
          <p class="muted">Score, cantidad de intentos y confianza por habilidad.</p>
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
            <p class="muted small">Habilidades practicadas</p>
            <p class="big-number">{{ d.skillsPracticed }}/{{ d.skillsTotal }}</p>
          </div>
        </section>

        @if (d.weakest.length) {
          <section class="card">
            <h2>Para reforzar</h2>
            <p class="muted small">Las próximas clases van a darle más peso a estas habilidades.</p>
            <div class="row">
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

        @for (area of d.areas; track area.key) {
          <section class="card">
            <div class="area-head">
              <h2>{{ area.name }}</h2>
              <strong>{{ area.score === null ? '—' : area.score + '%' }}</strong>
            </div>
            <div class="bar"><span [style.width.%]="area.score ?? 0"></span></div>

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
                        </span>
                      </div>
                      <div class="skill-score">
                        <span [class]="statusInfo(skill).chip">{{ statusInfo(skill).label }}</span>
                        <strong>{{ skill.score === null ? '' : skill.score + '%' }}</strong>
                      </div>
                    </li>
                  }
                </ul>
              </div>
            }
          </section>
        }
      }
    </main>
  `,
  styles: `
    .area-head, .topic-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
    .area-head h2 { margin: 0 0 0.5rem; }
    .topic { margin-top: 1.1rem; }
    .skill-name { display: flex; flex-direction: column; gap: 0.15rem; }
    .skill-score { display: flex; gap: 0.6rem; align-items: center; min-width: 150px; justify-content: flex-end; }
  `
})
export class DashboardComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly status = SKILL_STATUS;
  readonly confidence = CONFIDENCE;
  readonly trend = TREND;
  readonly scoreChip = scoreChip;
  readonly data = signal<Dashboard | null>(null);
  readonly loading = signal(true);

  statusInfo(skill: SkillProgress): { label: string; chip: string } {
    return this.status[skill.status] ?? this.status.NOT_STARTED;
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
