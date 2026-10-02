import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { AiSource, PlatformAccount, PlatformService, PlatformServiceDraft } from '../../core/models';
import { ToastService } from '../../core/toast.service';

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
    durationDays: null,
    dailyRequestLimit: null,
    description: null,
    active: true
  };
}

function numberOrNull(value: unknown): number | null {
  const n = Number(value);
  return value === null || value === '' || !Number.isFinite(n) || n <= 0 ? null : Math.round(n);
}

/** Portal (T-004 etapa 1): catálogo de servicios y asignación manual a cuentas. */
@Component({
  selector: 'app-services-admin',
  imports: [FormsModule, DatePipe],
  template: `
    <section class="card stack">
      <div class="section-head">
        <div>
          <h2>Servicios</h2>
          <p class="muted small">
            Vínculo × fuente de IA. Sin servicio otorgado, cada cuenta es
            <strong>Individual · propias keys</strong>.
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
            <label class="field">
              Duración (días)
              <input class="input" type="number" min="1" name="sDays" placeholder="sin vencimiento"
                [(ngModel)]="draft.durationDays" />
            </label>
            <label class="field">
              Tope diario de pedidos a la plataforma
              <input class="input" type="number" min="1" name="sLimit" placeholder="sin tope"
                [(ngModel)]="draft.dailyRequestLimit" />
            </label>
          </div>
          <label class="field">
            Descripción
            <input class="input" name="sDesc" [(ngModel)]="draft.description" maxlength="300" />
          </label>
          <label class="small check-row">
            <input type="checkbox" name="sActive" [(ngModel)]="draft.active" /> Activo (se puede otorgar)
          </label>
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
              <tr><th>Servicio</th><th>Fuente</th><th>Duración</th><th>Tope diario</th><th>Cuentas</th><th></th></tr>
            </thead>
            <tbody>
              @for (s of services(); track s.id) {
                <tr [class.inactive]="!s.active">
                  <td>
                    <strong>{{ s.name }}</strong>
                    @if (!s.active) { <span class="chip">Inactivo</span> }
                    @if (s.description) { <div class="muted small">{{ s.description }}</div> }
                  </td>
                  <td>{{ sourceShort[s.source] }}</td>
                  <td>{{ s.durationDays ? s.durationDays + ' días' : '—' }}</td>
                  <td>{{ s.dailyRequestLimit ?? '—' }}</td>
                  <td>{{ s.activeAccounts }}</td>
                  <td><button class="btn btn-sm" type="button" (click)="startEdit(s)">Editar</button></td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </section>

    <section class="card stack">
      <div>
        <h2>Cuentas y servicios</h2>
        <p class="muted small">Otorgá un servicio a una cuenta. Reemplaza al que tenga; al vencer vuelve a propias keys.</p>
      </div>
      <form class="row" (ngSubmit)="loadAccounts()">
        <input class="input search" name="q" [(ngModel)]="query" placeholder="Buscar por email o nombre" />
        <button class="btn btn-sm" type="submit" [disabled]="loadingAccounts()">Buscar</button>
      </form>

      @if (loadingAccounts()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else if (accounts().length === 0) {
        <p class="muted">Sin cuentas para esa búsqueda.</p>
      } @else {
        <ul class="list">
          @for (a of accounts(); track a.id) {
            <li class="list-item account">
              <div class="account-main">
                <div class="row">
                  <strong>{{ a.email }}</strong>
                  @if (a.isPlatformOwner) { <span class="chip">Dueño</span> }
                </div>
                <span class="small">
                  <span [class]="a.service.granted ? 'chip chip-ok' : 'chip'">{{ a.service.name }}</span>
                  @if (a.service.granted) {
                    @if (a.service.expiresAt) { · vence {{ a.service.expiresAt | date: 'dd/MM/yyyy HH:mm' }} }
                    @else { · sin vencimiento }
                  }
                  @if (a.service.expired) {
                    <span class="chip chip-warn">Venció {{ a.service.expired.name }}</span>
                  }
                </span>
                <span class="muted small">
                  Primera sesión:
                  @if (a.firstLoginAt) {
                    {{ a.firstLoginAt | date: 'dd/MM/yyyy HH:mm:ss' }}
                  } @else {
                    nunca ingresó
                  }
                  · {{ a.ownConnections }} conexión(es) propia(s)
                  · {{ a.platformRequests24h }} pedidos a la plataforma en 24 h
                </span>
              </div>
              <div class="row">
                @if (a.isPlatformOwner) {
                  <span class="muted small">Usa propias + plataforma</span>
                } @else {
                  <button class="btn btn-sm" type="button" (click)="startGrant(a)">Otorgar</button>
                  @if (a.service.granted) {
                    <button class="btn btn-sm btn-danger" type="button" (click)="revoke(a)" [disabled]="busyId() === a.id">Quitar</button>
                  }
                }
              </div>
              @if (grantingId() === a.id) {
                <form class="grant row" (ngSubmit)="grant(a)">
                  <label class="field">
                    Servicio
                    <select class="input" name="gService" [(ngModel)]="grantServiceId">
                      @for (s of grantable(); track s.id) {
                        <option [ngValue]="s.id">{{ s.name }}</option>
                      }
                    </select>
                  </label>
                  <label class="field">
                    Días
                    <input class="input days" type="number" min="1" name="gDays" [(ngModel)]="grantDays"
                      [placeholder]="defaultDaysLabel()" />
                  </label>
                  <button class="btn btn-primary btn-sm" type="submit" [disabled]="busyId() === a.id || !grantServiceId">
                    @if (busyId() === a.id) { <span class="spinner"></span> } Confirmar
                  </button>
                  <button class="btn btn-sm" type="button" (click)="grantingId.set(null)">Cancelar</button>
                </form>
              }
            </li>
          }
        </ul>
      }
    </section>
  `,
  styles: `
    :host { display: contents; }
    .section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
    .section-head h2, .section-head p { margin: 0; }
    .section-head p { margin-top: 0.3rem; }
    .edit, .grant { padding: 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; background: var(--bg); }
    .grant { width: 100%; align-items: flex-end; flex-wrap: wrap; }
    .check-row { display: flex; align-items: center; gap: 0.4rem; }
    .table-wrap { overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; font-size: 0.88rem; }
    th, td { text-align: left; padding: 0.45rem 0.8rem 0.45rem 0; border-bottom: 1px solid var(--border); vertical-align: top; }
    tr.inactive td { opacity: 0.6; }
    .search { max-width: 22rem; }
    .account { flex-wrap: wrap; }
    .account-main { display: flex; flex-direction: column; gap: 0.25rem; }
    .days { width: 7rem; }
  `
})
export class ServicesAdminComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);

  readonly sourceShort = SOURCE_SHORT;
  readonly services = signal<PlatformService[]>([]);
  readonly accounts = signal<PlatformAccount[]>([]);
  readonly loadingAccounts = signal(true);
  readonly saving = signal(false);
  readonly busyId = signal<number | null>(null);
  /** null: sin formulario · 0: nuevo · id: editando. */
  readonly editingId = signal<number | null>(null);
  readonly grantingId = signal<number | null>(null);
  readonly grantable = computed(() => this.services().filter((s) => s.active));

  draft: PlatformServiceDraft = emptyDraft();
  query = '';
  grantServiceId: number | null = null;
  grantDays: number | null = null;

  async ngOnInit(): Promise<void> {
    await Promise.all([this.loadServices(), this.loadAccounts()]);
  }

  async loadServices(): Promise<void> {
    try {
      this.services.set(await firstValueFrom(this.api.platformServices()));
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

  startEdit(s: PlatformService): void {
    const { id: _id, code: _code, activeAccounts: _n, ...draft } = s;
    this.draft = { ...draft };
    this.editingId.set(s.id);
  }

  async saveService(): Promise<void> {
    const id = this.editingId();
    const draft: PlatformServiceDraft = {
      ...this.draft,
      name: this.draft.name.trim(),
      durationDays: numberOrNull(this.draft.durationDays),
      dailyRequestLimit: numberOrNull(this.draft.dailyRequestLimit),
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
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }

  startGrant(a: PlatformAccount): void {
    const current = this.grantable().find((s) => s.code === a.service.code && a.service.granted);
    const platform = this.grantable().find((s) => s.source === 'PLATFORM');
    this.grantServiceId = (current ?? platform ?? this.grantable()[0])?.id ?? null;
    this.grantDays = null;
    this.grantingId.set(a.id);
  }

  defaultDaysLabel(): string {
    const s = this.services().find((x) => x.id === this.grantServiceId);
    return s?.durationDays ? `${s.durationDays} (del servicio)` : 'sin vencimiento';
  }

  async grant(a: PlatformAccount): Promise<void> {
    if (!this.grantServiceId) {
      return;
    }
    this.busyId.set(a.id);
    try {
      const updated = await firstValueFrom(
        this.api.grantService(a.id, this.grantServiceId, numberOrNull(this.grantDays))
      );
      this.replace(updated);
      this.grantingId.set(null);
      this.toast.success(`${updated.email}: ${updated.service.name}.`);
      await this.afterChange(a);
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busyId.set(null);
    }
  }

  async revoke(a: PlatformAccount): Promise<void> {
    if (!confirm(`¿Quitar "${a.service.name}" a ${a.email}? Vuelve a usar sus propias API keys.`)) {
      return;
    }
    this.busyId.set(a.id);
    try {
      this.replace(await firstValueFrom(this.api.revokeService(a.id)));
      this.toast.success('Servicio quitado.');
      await this.afterChange(a);
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busyId.set(null);
    }
  }

  private replace(updated: PlatformAccount): void {
    this.accounts.update((list) => list.map((a) => (a.id === updated.id ? updated : a)));
  }

  private async afterChange(a: PlatformAccount): Promise<void> {
    await this.loadServices();
    if (a.id === this.auth.me()?.account.id) {
      await this.auth.refreshMe();
    }
  }
}
