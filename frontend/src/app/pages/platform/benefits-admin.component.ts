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
  imports: [FormsModule],
  template: `
    <section class="card stack">
      <div class="section-head">
        <div>
          <h2>Beneficios</h2>
          <p class="muted small">
            Acá se define una sola vez <strong>qué se otorga</strong>: servicio + duración.
            Campañas e invitaciones reutilizan esta definición.
          </p>
        </div>
        @if (editingId() === null) {
          <button class="btn btn-sm" type="button" (click)="startNew()">Nuevo beneficio</button>
        }
      </div>

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
                placeholder="usa la duración del servicio" />
            </label>
          </div>
          <label class="check-row small">
            <input type="checkbox" name="bActive" [(ngModel)]="draft.active" />
            Activo para nuevos otorgamientos
          </label>
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
              <tr><th>Beneficio</th><th>Servicio</th><th>Duración</th><th>Usos</th><th></th></tr>
            </thead>
            <tbody>
              @for (benefit of benefits(); track benefit.id) {
                <tr [class.inactive]="!benefit.active">
                  <td>
                    <strong>{{ benefit.name }}</strong>
                    @if (!benefit.active) { <span class="chip">Inactivo</span> }
                  </td>
                  <td>{{ benefit.serviceName }}</td>
                  <td>{{ benefit.effectiveDurationDays ? benefit.effectiveDurationDays + ' días' : 'sin vencimiento' }}</td>
                  <td class="small">
                    {{ benefit.usedByCampaigns }} campaña(s) · {{ benefit.usedByInvitations }} invitación(es)
                  </td>
                  <td><button class="btn btn-sm" type="button" (click)="startEdit(benefit)">Editar</button></td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>
  `,
  styles: `
    :host { display: contents; }
    .section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
    .section-head h2, .section-head p { margin: 0; }
    .section-head p { margin-top: 0.3rem; }
    .editor { padding: 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; background: var(--bg); }
    .check-row { display: flex; align-items: center; gap: 0.45rem; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    th, td { text-align: left; padding: 0.45rem 0.8rem 0.45rem 0; border-bottom: 1px solid var(--border); vertical-align: top; }
    tr.inactive { opacity: 0.65; }
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
