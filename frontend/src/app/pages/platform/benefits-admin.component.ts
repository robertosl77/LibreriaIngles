import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import {
  PlatformBenefit,
  PlatformBenefitDraft,
  PlatformService
} from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';
import { ActiveToggleComponent } from './active-toggle.component';

function emptyDraft(serviceId: number | null): PlatformBenefitDraft {
  return {
    name: '',
    serviceId: serviceId ?? 0,
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
      description="Define qué se otorga: un servicio + su duración. Campañas, invitaciones y otorgamientos manuales reutilizan esta definición."
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
                placeholder="Ej. Plataforma 30 días" />
            </label>
            <label class="field">
              Servicio
              <select class="input" name="bService" [(ngModel)]="draft.serviceId" required>
                @for (service of grantableServices(); track service.id) {
                  <option [ngValue]="service.id">{{ service.name }}</option>
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
              [disabled]="saving() || !draft.name.trim() || !draft.serviceId">
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
                <th>Duración</th>
                <th>Usos</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (benefit of benefits(); track benefit.id) {
                <tr [class.inactive]="!benefit.active">
                  <td><strong>{{ benefit.name }}</strong></td>
                  <td>{{ benefit.serviceName }}</td>
                  <td>{{ benefit.durationDays ? benefit.durationDays + ' días' : 'sin vencimiento' }}</td>
                  <td class="small">
                    {{ benefit.usedByCampaigns }} campaña(s) · {{ benefit.usedByInvitations }} invitación(es)
                  </td>
                  <td>
                    <span [class]="benefit.active ? 'chip chip-ok' : 'chip'">
                      {{ benefit.active ? 'Activo' : 'Inactivo' }}
                    </span>
                  </td>
                  <td>
                    <button class="btn btn-sm" type="button" (click)="startEdit(benefit)">Editar</button>
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
export class BenefitsAdminComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly benefits = signal<PlatformBenefit[]>([]);
  readonly services = signal<PlatformService[]>([]);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly editingId = signal<number | null>(null);
  readonly grantableServices = computed(() =>
    this.services().filter((service) => service.active && service.linkType === 'PERSONAL')
  );

  draft: PlatformBenefitDraft = emptyDraft(null);

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const [benefits, services] = await Promise.all([
        firstValueFrom(this.api.platformBenefits()),
        firstValueFrom(this.api.platformServices())
      ]);
      this.benefits.set(benefits);
      this.services.set(services);
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  startNew(): void {
    this.draft = emptyDraft(this.grantableServices()[0]?.id ?? null);
    this.editingId.set(0);
  }

  startEdit(benefit: PlatformBenefit): void {
    this.draft = {
      name: benefit.name,
      serviceId: benefit.serviceId,
      durationDays: benefit.durationDays,
      active: benefit.active
    };
    this.editingId.set(benefit.id);
  }

  async save(): Promise<void> {
    const id = this.editingId();
    if (id === null || !this.draft.serviceId) return;
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
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }
}
