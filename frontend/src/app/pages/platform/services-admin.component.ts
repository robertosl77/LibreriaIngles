import { DatePipe } from '@angular/common';
import { Component, Input, OnChanges, OnInit, SimpleChanges, computed, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import {
  AiSource,
  PlatformAccount,
  PlatformBenefit,
  PlatformService,
  PlatformServiceDraft
} from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';
import { ActiveToggleComponent } from '../../shared/ui/active-toggle.component';

const SOURCE_SHORT: Record<AiSource, string> = {
  BYOK: 'Propias keys',
  PLATFORM: 'Plataforma',
  HYBRID: 'Híbrido'
};

function emptyDraft(): PlatformServiceDraft {
  return {
    name: '',
    source: 'PLATFORM',
    linkType: 'PERSONAL',
    description: null,
    active: true
  };
}

/** Portal (T-004): catálogo de capacidades + cuentas. La vigencia vive en Beneficios. */
@Component({
  selector: 'app-services-admin',
  imports: [FormsModule, DatePipe, ActiveToggleComponent, CollapseCardComponent],
  template: `
    <section class="card stack">
      <div class="section-head">
        <div>
          <h2>Servicios</h2>
          <p class="muted small">
            Define <strong>qué servicio existe</strong>: vínculo, fuente de IA y descripción.
            La duración se configura en Beneficios y los límites de consumo en cada conexión de IA.
          </p>
        </div>
        @if (editingId() === null) {
          <button class="btn btn-sm" type="button" (click)="startNew()">Nuevo servicio</button>
        }
      </div>

      @if (editingId() !== null) {
        <form class="edit stack" (ngSubmit)="saveService()">
          <div class="grid">
            <label class="field">
              Nombre
              <input class="input" name="sName" [(ngModel)]="draft.name" required maxlength="120" />
            </label>
            <label class="field">
              Fuente de IA
              <select class="input" name="sSource" [(ngModel)]="draft.source">
                <option value="BYOK">Propias keys (BYOK)</option>
                <option value="PLATFORM">Plataforma</option>
                <option value="HYBRID">Híbrido (propias, si fallan plataforma)</option>
              </select>
            </label>
          </div>

          <label class="field">
            Descripción
            <input class="input" name="sDesc" [(ngModel)]="draft.description" maxlength="300" />
          </label>

          <div class="state-row">
            <div>
              <strong class="small">Estado</strong>
              <div class="muted tiny">Determina si puede usarse en nuevos beneficios.</div>
            </div>
            <app-active-toggle [(value)]="draft.active" />
          </div>

          <p class="muted small">Vínculo: personal. Los servicios corporativos llegan con las empresas.</p>
          <div class="row">
            <button class="btn btn-primary btn-sm" type="submit" [disabled]="saving() || !draft.name.trim()">
              @if (saving()) { <span class="spinner"></span> } Guardar
            </button>
            <button class="btn btn-sm" type="button" (click)="editingId.set(null)">Cancelar</button>
          </div>
        </form>
      }

      @if (services().length) {
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Servicio</th>
                <th>Fuente</th>
                <th>Cuentas</th>
                <th>Estado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (s of services(); track s.id) {
                <tr [class.inactive]="!s.active">
                  <td>
                    <strong>{{ s.name }}</strong>
                    @if (s.description) { <div class="muted small">{{ s.description }}</div> }
                  </td>
                  <td>{{ sourceShort[s.source] }}</td>
                  <td>{{ s.activeAccounts }}</td>
                  <td>
                    <span [class]="s.active ? 'chip chip-ok' : 'chip'">
                      {{ s.active ? 'Activo' : 'Inactivo' }}
                    </span>
                  </td>
                  <td><button class="btn btn-sm" type="button" (click)="startEdit(s)">Editar</button></td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>

    <app-collapse-card
      title="Cuentas"
      description="Administrá el beneficio asignado a cada cuenta. El servicio resultante queda como detalle."
    >
      <form class="row search-row" (ngSubmit)="loadAccounts()">
        <input class="input search" name="q" [(ngModel)]="query" placeholder="Buscar por email o nombre" />
        <button class="btn btn-sm" type="submit" [disabled]="loadingAccounts()">Buscar</button>
      </form>

      @if (loadingAccounts()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else if (accounts().length === 0) {
        <p class="muted">Sin cuentas para esa búsqueda.</p>
      } @else {
        <div class="accounts">
          @for (a of accounts(); track a.id) {
            <article class="account-card">
              <div class="account-line">
                <div class="identity">
                  <strong>{{ a.email }}</strong>
                  @if (a.isPlatformOwner) { <span class="chip">Dueño</span> }
                </div>

                <div class="service-cell">
                  @if (a.service.granted) {
                    <span class="chip chip-ok">{{ a.service.benefitName ?? 'Beneficio sin identificar' }}</span>
                    <span class="muted small">Servicio: {{ a.service.name }}</span>
                    <span class="small">
                      @if (a.service.expiresAt) {
                        vence {{ a.service.expiresAt | date: 'dd/MM/yyyy HH:mm' }}
                      } @else {
                        sin vencimiento
                      }
                    </span>
                  } @else {
                    <span class="chip">Sin beneficio</span>
                    <span class="muted small">Servicio: {{ a.service.name }}</span>
                  }
                  @if (a.service.expired) {
                    <span class="chip chip-warn">Venció {{ a.service.expired.name }}</span>
                  }
                </div>

                <div class="account-actions">
                  @if (a.isPlatformOwner) {
                    <span class="muted small">Usa propias + plataforma</span>
                  } @else {
                    <button class="btn btn-sm" type="button" (click)="toggleManage(a)">
                      {{ grantingId() === a.id ? 'Cerrar' : 'Administrar' }}
                    </button>
                  }
                </div>
              </div>

              <div class="account-meta">
                Primera sesión:
                @if (a.firstLoginAt) {
                  {{ a.firstLoginAt | date: 'dd/MM/yyyy HH:mm:ss' }}
                } @else {
                  nunca ingresó
                }
                · {{ a.ownConnections }} conexión(es) propia(s)
                · {{ a.platformRequests24h }} pedidos a la plataforma en 24 h
              </div>

              @if (grantingId() === a.id) {
                <div class="account-admin">
                  <div class="admin-benefit">
                    <label class="field benefit-field">
                      Beneficio
                      <select class="input" name="gBenefit{{ a.id }}" [(ngModel)]="grantBenefitId">
                        @for (benefit of grantableBenefits(); track benefit.id) {
                          <option [ngValue]="benefit.id">{{ benefit.name }}</option>
                        }
                      </select>
                    </label>
                    <p class="muted small">
                      Cambiar reemplaza el beneficio vigente. La asignación anterior queda en el historial.
                    </p>
                  </div>

                  <div class="admin-actions">
                    <button class="btn btn-primary btn-sm" type="button" (click)="grant(a)"
                      [disabled]="busyId() === a.id || !grantBenefitId">
                      @if (busyId() === a.id) { <span class="spinner"></span> }
                      {{ a.service.granted ? 'Cambiar beneficio' : 'Otorgar beneficio' }}
                    </button>
                    <button class="btn btn-sm btn-danger" type="button" (click)="revoke(a)"
                      [disabled]="busyId() === a.id || !a.service.granted">
                      Quitar beneficio
                    </button>
                    @if (a.devPurgeAllowed) {
                      <button class="btn btn-sm btn-danger" type="button" (click)="purge(a)"
                        [disabled]="busyId() === a.id">
                        Eliminar cuenta (DEV)
                      </button>
                    }
                  </div>
                </div>
              }
            </article>
          }
        </div>
      }
    </app-collapse-card>
  `,
  styles: `
    :host { display: contents; }
    .section-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .section-head h2, .section-head p { margin: 0; }
    .section-head p { margin-top: 0.3rem; }
    .edit, .account-admin {
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
    table { border-collapse: collapse; width: 100%; font-size: 0.88rem; }
    th, td {
      text-align: left;
      padding: 0.45rem 0.8rem 0.45rem 0;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }
    tr.inactive td { opacity: 0.62; }
    .search-row { align-items: center; }
    .search { max-width: 22rem; }
    .accounts { display: flex; flex-direction: column; }
    .account-card {
      padding: 0.8rem 0;
      border-bottom: 1px solid var(--border);
    }
    .account-card:first-child { padding-top: 0.2rem; }
    .account-line {
      display: grid;
      grid-template-columns: minmax(13rem, 1.25fr) minmax(17rem, 1.2fr) auto;
      gap: 1rem;
      align-items: center;
    }
    .identity, .service-cell, .account-actions {
      display: flex;
      align-items: center;
      gap: 0.45rem;
      flex-wrap: wrap;
      min-width: 0;
    }
    .account-actions {
      justify-content: flex-end;
      flex-wrap: nowrap;
    }
    .account-meta {
      margin-top: 0.35rem;
      color: var(--muted);
      font-size: 0.82rem;
    }
    .account-admin {
      display: grid;
      grid-template-columns: minmax(18rem, 1fr) auto;
      gap: 1rem;
      align-items: end;
      margin-top: 0.7rem;
    }
    .admin-benefit p { margin: 0.35rem 0 0; }
    .admin-actions {
      display: flex;
      gap: 0.45rem;
      justify-content: flex-end;
      flex-wrap: wrap;
      align-items: center;
    }

    @media (max-width: 980px) {
      .account-line {
        grid-template-columns: 1fr;
        gap: 0.45rem;
      }
      .account-actions { justify-content: flex-start; flex-wrap: wrap; }
      .account-admin { grid-template-columns: 1fr; }
      .admin-actions { justify-content: flex-start; }
    }
  `
})
export class ServicesAdminComponent implements OnInit, OnChanges {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);

  @Input() refreshVersion = 0;
  readonly changed = output<void>();

  readonly sourceShort = SOURCE_SHORT;
  readonly services = signal<PlatformService[]>([]);
  readonly benefits = signal<PlatformBenefit[]>([]);
  readonly accounts = signal<PlatformAccount[]>([]);
  readonly loadingAccounts = signal(true);
  readonly saving = signal(false);
  readonly busyId = signal<number | null>(null);
  /** null: sin formulario · 0: nuevo · id: editando. */
  readonly editingId = signal<number | null>(null);
  readonly grantingId = signal<number | null>(null);

  readonly grantableBenefits = computed(() => {
    const activeServiceIds = new Set(
      this.services().filter((service) => service.active).map((service) => service.id)
    );
    return this.benefits().filter(
      (benefit) => benefit.active && activeServiceIds.has(benefit.serviceId)
    );
  });

  draft: PlatformServiceDraft = emptyDraft();
  query = '';
  grantBenefitId: number | null = null;

  async ngOnInit(): Promise<void> {
    await Promise.all([this.loadServices(), this.loadBenefits(), this.loadAccounts()]);
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['refreshVersion'] && !changes['refreshVersion'].firstChange) {
      void Promise.all([this.loadBenefits(), this.loadAccounts()]);
    }
  }

  async loadServices(): Promise<void> {
    try {
      this.services.set(await firstValueFrom(this.api.platformServices()));
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }

  async loadBenefits(): Promise<void> {
    try {
      this.benefits.set(await firstValueFrom(this.api.platformBenefits()));
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }

  async loadAccounts(): Promise<void> {
    this.loadingAccounts.set(true);
    try {
      this.accounts.set(await firstValueFrom(this.api.platformAccounts(this.query)));
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loadingAccounts.set(false);
    }
  }

  startNew(): void {
    this.draft = emptyDraft();
    this.editingId.set(0);
  }

  startEdit(service: PlatformService): void {
    const { id: _id, code: _code, activeAccounts: _n, ...draft } = service;
    this.draft = { ...draft };
    this.editingId.set(service.id);
  }

  async saveService(): Promise<void> {
    const id = this.editingId();
    const draft: PlatformServiceDraft = {
      ...this.draft,
      name: this.draft.name.trim(),
      description: this.draft.description?.trim() || null
    };
    this.saving.set(true);
    try {
      await firstValueFrom(
        id ? this.api.updatePlatformService(id, draft) : this.api.createPlatformService(draft)
      );
      this.toast.success(id ? 'Servicio actualizado.' : 'Servicio creado.');
      this.editingId.set(null);
      await Promise.all([this.loadServices(), this.loadAccounts()]);
      this.changed.emit();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }

  toggleManage(account: PlatformAccount): void {
    if (this.grantingId() === account.id) {
      this.grantingId.set(null);
      return;
    }
    const currentBenefit = account.service.benefitId
      ? this.grantableBenefits().find((benefit) => benefit.id === account.service.benefitId)
      : undefined;
    this.grantBenefitId = (currentBenefit ?? this.grantableBenefits()[0])?.id ?? null;
    this.grantingId.set(account.id);
  }

  async grant(account: PlatformAccount): Promise<void> {
    if (!this.grantBenefitId) return;
    this.busyId.set(account.id);
    try {
      const updated = await firstValueFrom(
        this.api.grantBenefit(account.id, this.grantBenefitId)
      );
      this.replace(updated);
      this.grantingId.set(null);
      this.toast.success(
        `${updated.email}: beneficio · ${updated.service.benefitName ?? 'actualizado'}.`
      );
      await this.afterChange(account);
      this.changed.emit();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busyId.set(null);
    }
  }

  async revoke(account: PlatformAccount): Promise<void> {
    const currentName = account.service.benefitName ?? account.service.name;
    if (!confirm(`¿Quitar "${currentName}" a ${account.email}? Vuelve a usar sus propias API keys.`)) {
      return;
    }
    this.busyId.set(account.id);
    try {
      this.replace(await firstValueFrom(this.api.revokeService(account.id)));
      this.toast.success('Beneficio quitado.');
      await this.afterChange(account);
      this.changed.emit();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busyId.set(null);
    }
  }

  async purge(account: PlatformAccount): Promise<void> {
    const confirmed = confirm(
      'DEV: ¿Eliminar completamente ' + account.email + '?\n\n' +
      'Se borrarán cuenta, perfil, clases, progreso, intentos, IA, campañas recibidas y servicios. ' +
      'Esta acción no se puede deshacer.'
    );
    if (!confirmed) return;

    this.busyId.set(account.id);
    try {
      await firstValueFrom(this.api.devPurgePlatformAccount(account.id));
      this.accounts.update((list) => list.filter((item) => item.id !== account.id));
      this.toast.success(account.email + ' fue eliminada completamente.');
      await this.loadServices();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busyId.set(null);
    }
  }

  private replace(updated: PlatformAccount): void {
    this.accounts.update((list) => list.map((account) =>
      account.id === updated.id ? updated : account
    ));
  }

  private async afterChange(account: PlatformAccount): Promise<void> {
    await this.loadServices();
    if (account.id === this.auth.me()?.account.id) {
      await this.auth.refreshMe();
    }
  }
}
