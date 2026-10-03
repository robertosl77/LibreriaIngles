import { Component, Input, OnChanges, OnInit, SimpleChanges, computed, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import {
  AiSource,
  LinkType,
  PlatformBenefit,
  PlatformBenefitDraft,
  PlatformService
} from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';
import { ActiveToggleComponent } from '../../shared/ui/active-toggle.component';

const SOURCE_SHORT: Record<AiSource, string> = {
  BYOK: 'Propias keys (BYOK)',
  PLATFORM: 'Plataforma',
  HYBRID: 'Híbrido'
};

const SERVICE_SHORT: Record<LinkType, string> = {
  PERSONAL: 'Personal',
  CORPORATE: 'Corporativa'
};

function emptyDraft(source: AiSource = 'BYOK'): PlatformBenefitDraft {
  return {
    name: '',
    service: 'PERSONAL',
    source,
    durationDays: null,
    active: true
  };
}

function numberOrNull(value: unknown): number | null {
  const n = Number(value);
  return value === null || value === '' || !Number.isFinite(n) || n <= 0 ? null : Math.round(n);
}

@Component({
  selector: 'app-benefits-admin',
  imports: [FormsModule, ActiveToggleComponent, CollapseCardComponent],
  template: `
    <app-collapse-card
      title="Beneficios"
      description="Define qué se otorga: servicio + fuente de IA + duración. Campañas, invitaciones y otorgamientos manuales reutilizan esta definición."
    >
      @if (editingId() === null) {
        <div class="collapse-actions">
          <button class="btn btn-sm" type="button" (click)="startNew()">Nuevo beneficio</button>
        </div>
      }

      @if (editingId() !== null) {
        <form class="editor stack" (ngSubmit)="save()">
          <div class="grid">
            <label class="field">
              Nombre
              <input class="input" name="bName" [(ngModel)]="draft.name" required maxlength="120"
                placeholder="Ej. Regalo 30 días" />
            </label>

            <label class="field">
              Servicio
              <select class="input" name="bService" [(ngModel)]="draft.service" (ngModelChange)="ensureSource()">
                <option value="PERSONAL">Personal</option>
              </select>
            </label>

            <label class="field">
              Fuente de IA
              <select class="input" name="bSource" [(ngModel)]="draft.source" required>
                @for (item of availableCombinations(); track item.id) {
                  <option [ngValue]="item.source" [disabled]="!item.active">
                    {{ sourceShort[item.source] }}{{ item.active ? '' : ' · deshabilitada' }}
                  </option>
                }
              </select>
            </label>

            <label class="field">
              Duración (días)
              <input class="input" type="number" min="1" name="bDays" [(ngModel)]="draft.durationDays"
                placeholder="sin vencimiento" />
              <span class="muted tiny">Vacío = el beneficio no vence.</span>
            </label>
          </div>

          <div class="state-row">
            <div>
              <strong class="small">Estado</strong>
              <div class="muted tiny">Determina si puede usarse en nuevos otorgamientos.</div>
            </div>
            <app-active-toggle [(value)]="draft.active" />
          </div>

          @if (editingId()) {
            <p class="banner small">
              Cambiar este beneficio modifica los <strong>futuros</strong> otorgamientos de todas las
              campañas e invitaciones que lo usan. Los canjes ya realizados conservan su historial.
            </p>
          }

          <div class="row">
            <button class="btn btn-primary btn-sm" type="submit"
              [disabled]="saving() || !draft.name.trim() || !canSaveCombination()">
              @if (saving()) { <span class="spinner"></span> } Guardar
            </button>
            <button class="btn btn-sm" type="button" (click)="editingId.set(null)">Cancelar</button>
          </div>
        </form>
      }

      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else {
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Beneficio</th>
                <th>Servicio</th>
                <th>Fuente</th>
                <th>Duración</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (benefit of benefits(); track benefit.id) {
                <tr [class.inactive]="!benefit.active">
                  <td><strong>{{ benefit.name }}</strong></td>
                  <td>{{ benefit.serviceName }}</td>
                  <td>{{ sourceShort[benefit.source] }}</td>
                  <td>{{ benefit.durationDays ? benefit.durationDays + ' días' : 'sin vencimiento' }}</td>
                  <td>
                    <span [class]="benefit.active ? 'chip chip-ok' : 'chip'">
                      {{ benefit.active ? 'Activo' : 'Inactivo' }}
                    </span>
                  </td>
                  <td>
                    <button class="btn btn-sm" type="button" (click)="startEdit(benefit)">Editar</button>
                    <button
                      class="btn btn-sm btn-danger"
                      type="button"
                      (click)="remove(benefit)"
                      [disabled]="!benefit.canDelete"
                      [title]="deleteReason(benefit)"
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </app-collapse-card>
  `,
  styles: `
    :host { display: contents; }
    .collapse-actions { display: flex; justify-content: flex-end; margin-bottom: 0.8rem; }
    .editor {
      padding: 0.8rem;
      border: 1px solid var(--border);
      border-radius: 0.6rem;
      background: var(--bg);
    }
    .state-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .tiny { font-size: 0.76rem; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    th, td {
      text-align: left;
      padding: 0.45rem 0.8rem 0.45rem 0;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }
    tr.inactive { opacity: 0.62; }
  `
})
export class BenefitsAdminComponent implements OnInit, OnChanges {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  @Input() refreshVersion = 0;
  readonly benefits = signal<PlatformBenefit[]>([]);
  readonly combinations = signal<PlatformService[]>([]);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly editingId = signal<number | null>(null);
  readonly changed = output<void>();
  readonly sourceShort = SOURCE_SHORT;
  readonly serviceShort = SERVICE_SHORT;

  draft: PlatformBenefitDraft = emptyDraft();

  readonly editingBenefit = computed(() =>
    this.benefits().find((benefit) => benefit.id === this.editingId()) ?? null
  );

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['refreshVersion'] && !changes['refreshVersion'].firstChange) {
      void this.load();
    }
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const [benefits, combinations] = await Promise.all([
        firstValueFrom(this.api.platformBenefits()),
        firstValueFrom(this.api.platformServices())
      ]);
      this.benefits.set(benefits);
      this.combinations.set(combinations);
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  availableCombinations(): PlatformService[] {
    const currentId = this.editingBenefit()?.combinationId ?? null;
    return this.combinations().filter(
      (item) =>
        item.linkType === this.draft.service &&
        (item.active || item.id === currentId)
    );
  }

  canSaveCombination(): boolean {
    const selected = this.availableCombinations().find((item) => item.source === this.draft.source);
    return !!selected && (selected.active || !this.draft.active);
  }

  ensureSource(): void {
    const options = this.availableCombinations();
    if (!options.some((item) => item.source === this.draft.source)) {
      this.draft.source = options.find((item) => item.active)?.source ?? 'BYOK';
    }
  }

  startNew(): void {
    const first = this.combinations().find(
      (item) => item.linkType === 'PERSONAL' && item.active
    );
    this.draft = emptyDraft(first?.source ?? 'BYOK');
    this.editingId.set(0);
  }

  startEdit(benefit: PlatformBenefit): void {
    this.draft = {
      name: benefit.name,
      service: benefit.service,
      source: benefit.source,
      durationDays: benefit.durationDays,
      active: benefit.active
    };
    this.editingId.set(benefit.id);
  }

  async save(): Promise<void> {
    const id = this.editingId();
    if (id === null || !this.canSaveCombination()) return;
    const draft: PlatformBenefitDraft = {
      ...this.draft,
      name: this.draft.name.trim(),
      durationDays: numberOrNull(this.draft.durationDays)
    };
    this.saving.set(true);
    try {
      await firstValueFrom(
        id ? this.api.updatePlatformBenefit(id, draft) : this.api.createPlatformBenefit(draft)
      );
      this.toast.success(id ? 'Beneficio actualizado.' : 'Beneficio creado.');
      this.editingId.set(null);
      await this.load();
      this.changed.emit();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }

  deleteReason(benefit: PlatformBenefit): string {
    if (benefit.canDelete) return 'Dar de baja lógicamente. El historial se conserva.';
    const blockers: string[] = [];
    if (benefit.activeBeneficiaries) blockers.push(`${benefit.activeBeneficiaries} beneficiario(s) vigente(s)`);
    if (benefit.activeCampaigns) blockers.push(`${benefit.activeCampaigns} campaña(s) activa(s)/pausada(s)`);
    if (benefit.activeInvitations) blockers.push(`${benefit.activeInvitations} invitación(es) vigente(s)`);
    return 'No se puede eliminar: ' + blockers.join(', ') + '.';
  }

  async remove(benefit: PlatformBenefit): Promise<void> {
    if (!benefit.canDelete) return;
    if (!confirm('¿Dar de baja el beneficio "' + benefit.name + '"? El historial se conserva.')) return;
    try {
      await firstValueFrom(this.api.deletePlatformBenefit(benefit.id));
      this.toast.success('Beneficio dado de baja.');
      if (this.editingId() === benefit.id) this.editingId.set(null);
      await this.load();
      this.changed.emit();
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }
}
