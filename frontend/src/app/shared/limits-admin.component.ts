import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../core/api.service';
import { LimitDefinition, PlanLimits, PlatformLimits } from '../core/models';

/**
 * T-220 (N-01): todos los límites en un solo lugar. Cada límite tiene un valor de plataforma y cada
 * servicio puede pisarlo; vacío en un servicio = hereda el de la plataforma.
 */
@Component({
  selector: 'app-limits-admin',
  template: `
    <section class="card stack">
      <div>
        <h2>Límites</h2>
        <p class="muted small">
          Un solo lugar para los topes. El valor de la plataforma rige para todos; un servicio puede
          tener el suyo (vacío = usa el de la plataforma). En la plataforma, vacío = sin tope. Vos no
          tenés tope.
        </p>
      </div>

      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else if (data(); as d) {
        <div class="table-wrap">
          <table class="limits">
            <thead>
              <tr>
                <th scope="col"></th>
                @for (def of d.definitions; track def.key) {
                  <th scope="col" [title]="def.description">{{ def.label }} <span class="muted tiny">({{ def.unit }})</span></th>
                }
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">Plataforma</th>
                @for (def of d.definitions; track def.key) {
                  <td>
                    <input
                      type="number"
                      min="1"
                      placeholder="Sin tope"
                      [value]="draft.platform[def.key] ?? ''"
                      (input)="setPlatform(def.key, $any($event.target).value)"
                      [attr.aria-label]="def.label + ' · plataforma'"
                    />
                  </td>
                }
              </tr>
              @for (plan of plans(); track plan.id) {
                <tr>
                  <th scope="row">{{ plan.name }}</th>
                  @for (def of d.definitions; track def.key) {
                    <td>
                      <input
                        type="number"
                        min="1"
                        [placeholder]="inheritLabel(def)"
                        [value]="draft.plans[plan.id][def.key] ?? ''"
                        (input)="setPlan(plan.id, def.key, $any($event.target).value)"
                        [attr.aria-label]="def.label + ' · ' + plan.name"
                      />
                    </td>
                  }
                </tr>
              }
            </tbody>
          </table>
        </div>
        <div class="row">
          <button type="button" class="button" [disabled]="saving()" (click)="save()">Guardar</button>
          @if (message()) { <span class="small muted">{{ message() }}</span> }
        </div>
      }
    </section>
  `,
  styles: `
    .table-wrap { overflow-x: auto; }
    .limits { border-collapse: collapse; width: 100%; }
    .limits th, .limits td { padding: 0.4rem 0.5rem; text-align: left; border-bottom: 1px solid var(--border); }
    .limits thead th { font-size: 0.85rem; font-weight: 600; }
    .limits tbody th { font-weight: 600; white-space: nowrap; }
    .limits input { width: 8rem; }
  `
})
export class LimitsAdminComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly message = signal('');
  readonly data = signal<PlatformLimits | null>(null);
  /** Los límites de IA de plataforma no aplican a servicios con keys propias. */
  readonly plans = computed<PlanLimits[]>(() =>
    (this.data()?.plans ?? []).filter((plan) => plan.active && plan.source !== 'BYOK')
  );

  draft: { platform: Record<string, number | null>; plans: Record<number, Record<string, number | null>> } = {
    platform: {},
    plans: {}
  };

  async ngOnInit(): Promise<void> {
    try {
      this.apply(await firstValueFrom(this.api.platformLimits()));
    } catch (err) {
      this.message.set(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  inheritLabel(def: LimitDefinition): string {
    const value = this.draft.platform[def.key];
    return value ? `Plataforma (${value})` : 'Plataforma (sin tope)';
  }

  setPlatform(key: string, raw: string): void {
    this.draft.platform[key] = this.parse(raw);
  }

  setPlan(planId: number, key: string, raw: string): void {
    this.draft.plans[planId][key] = this.parse(raw);
  }

  async save(): Promise<void> {
    const all = [
      ...Object.values(this.draft.platform),
      ...Object.values(this.draft.plans).flatMap((values) => Object.values(values))
    ];
    if (all.some((value) => value !== null && (!Number.isInteger(value) || value < 1))) {
      this.message.set('Cada tope tiene que ser un número entero, 1 o más.');
      return;
    }
    // Un servicio sin valor no manda la clave: hereda la plataforma.
    const plans: Record<number, Record<string, number | null>> = {};
    for (const [id, values] of Object.entries(this.draft.plans)) {
      plans[Number(id)] = Object.fromEntries(Object.entries(values).filter(([, value]) => value !== null));
    }
    this.saving.set(true);
    try {
      this.apply(await firstValueFrom(this.api.setPlatformLimits({ platform: this.draft.platform, plans })));
      this.message.set('Guardado.');
    } catch (err) {
      this.message.set(errorMessage(err, 'No se pudo guardar.'));
    } finally {
      this.saving.set(false);
    }
  }

  private apply(data: PlatformLimits): void {
    this.data.set(data);
    this.draft = {
      platform: Object.fromEntries(data.definitions.map((def) => [def.key, def.platformValue])),
      plans: Object.fromEntries(data.plans.map((plan) => [plan.id, { ...plan.values }]))
    };
  }

  private parse(raw: string): number | null {
    const text = raw.trim();
    return text === '' ? null : Number(text);
  }
}
