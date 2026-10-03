import { DatePipe } from '@angular/common';
import { Component, Input, OnChanges, OnInit, SimpleChanges, computed, inject, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { AiSource, PlatformAccount, PlatformBenefit } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';

const SOURCE_SHORT: Record<AiSource, string> = {
  BYOK: 'Propias keys',
  PLATFORM: 'Plataforma',
  HYBRID: 'Híbrido'
};

@Component({
  selector: 'app-accounts-admin',
  imports: [DatePipe, FormsModule, CollapseCardComponent],
  template: `
    <app-collapse-card
      title="Cuentas"
      description="Administrá beneficios y acciones puntuales sobre las cuentas."
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
        <div class="accounts" role="table" aria-label="Cuentas">
          <div class="acc-row acc-head" role="row">
            <span role="columnheader">Cuenta</span>
            <span role="columnheader">Beneficio</span>
            <span role="columnheader">IA que usa</span>
            <span role="columnheader">Vence</span>
            <span role="columnheader">Actividad</span>
            <span role="columnheader" class="sr-only">Acciones</span>
          </div>

          @for (a of accounts(); track a.id) {
            <div class="acc-item" [class.open]="grantingId() === a.id">
              <div class="acc-row" role="row">
                <div class="cell" role="cell" data-label="Cuenta">
                  <span class="email" [attr.title]="a.email">
                    <span class="email-text">{{ a.email }}</span>
                    @if (a.isPlatformOwner) { <span class="chip">Dueño</span> }
                  </span>
                  <span class="sub">
                    @if (a.firstLoginAt) {
                      1ª sesión {{ a.firstLoginAt | date: 'dd/MM/yy HH:mm' }}
                    } @else {
                      Nunca ingresó
                    }
                  </span>
                </div>

                <div class="cell" role="cell" data-label="Beneficio">
                  @if (a.service.granted) {
                    <span class="chip chip-ok" [attr.title]="a.service.benefitName">{{ a.service.benefitName ?? 'Sin identificar' }}</span>
                  } @else {
                    <span class="none">Sin beneficio</span>
                  }
                  @if (a.service.expired) {
                    <span class="chip chip-warn">Venció {{ a.service.expired.name }}</span>
                  }
                </div>

                <div class="cell" role="cell" data-label="IA que usa">
                  <span>{{ a.isPlatformOwner ? 'Propias + plataforma' : sourceShort[a.service.source] }}</span>
                  @if (a.service.linkType === 'CORPORATE') { <span class="sub">Corporativa</span> }
                </div>

                <div class="cell" role="cell" data-label="Vence">
                  @if (a.service.granted && a.service.expiresAt) {
                    <span>{{ a.service.expiresAt | date: 'dd/MM/yy HH:mm' }}</span>
                    <span class="sub">{{ daysLeft(a.service.expiresAt) }}</span>
                  } @else if (a.service.granted) {
                    <span>Sin vencimiento</span>
                  } @else {
                    <span class="none">—</span>
                  }
                </div>

                <div class="cell" role="cell" data-label="Actividad">
                  <span>{{ a.platformRequests24h }} {{ a.platformRequests24h === 1 ? 'pedido' : 'pedidos' }}</span>
                  <span class="sub">en 24 h · {{ a.ownConnections }} {{ a.ownConnections === 1 ? 'key' : 'keys' }}</span>
                </div>

                <div class="cell actions" role="cell">
                  @if (!a.isPlatformOwner) {
                    <button class="btn btn-sm" type="button" (click)="toggleManage(a)">
                      {{ grantingId() === a.id ? 'Cerrar' : 'Administrar' }}
                    </button>
                  }
                </div>
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
            </div>
          }
        </div>
      }
    </app-collapse-card>
  `,
  styles: `
    :host { display: contents; }

    .search-row { align-items: center; margin-bottom: 0.4rem; }
    .search { max-width: 22rem; }
    .accounts { display: flex; flex-direction: column; }

    .acc-row {
      display: grid;
      grid-template-columns: minmax(0, 1.6fr) minmax(0, 1.3fr) minmax(0, 0.8fr) minmax(0, 0.9fr) minmax(0, 0.8fr) 6.8rem;
      gap: 1rem;
      align-items: center;
      padding: 0.7rem 0.4rem;
    }

    .acc-head {
      padding-top: 0.4rem;
      padding-bottom: 0.45rem;
      border-bottom: 1px solid var(--border);
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--muted);
    }

    .acc-item { border-bottom: 1px solid var(--border); }
    .acc-item:last-child { border-bottom: 0; }
    .acc-item:hover > .acc-row, .acc-item.open > .acc-row { background: var(--bg); }
    .acc-item > .acc-row { border-radius: 0.5rem; }

    .cell { display: flex; flex-direction: column; align-items: flex-start; gap: 0.2rem; min-width: 0; font-size: 0.9rem; }
    .email { font-weight: 650; display: flex; align-items: center; gap: 0.4rem; max-width: 100%; }
    .email-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
    .cell .chip { max-width: 100%; white-space: normal; line-height: 1.25; }
    .sub { color: var(--muted); font-size: 0.78rem; }
    .none { color: var(--muted); }
    .actions { align-items: flex-end; }

    .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

    .account-admin {
      display: grid;
      grid-template-columns: minmax(18rem, 1fr) auto;
      gap: 1rem;
      align-items: end;
      margin: 0 0.4rem 0.8rem;
      padding: 0.8rem;
      border: 1px solid var(--border);
      border-radius: 0.6rem;
      background: var(--bg);
    }

    .admin-benefit p { margin: 0.35rem 0 0; }
    .admin-actions {
      display: flex;
      gap: 0.45rem;
      justify-content: flex-end;
      flex-wrap: wrap;
      align-items: center;
    }

    @media (max-width: 900px) {
      .acc-head { display: none; }
      .acc-row { grid-template-columns: 1fr 1fr; gap: 0.6rem 1rem; }
      .cell[data-label]::before {
        content: attr(data-label);
        font-size: 0.68rem; font-weight: 700; letter-spacing: 0.04em;
        text-transform: uppercase; color: var(--muted);
      }
      .cell[data-label="Cuenta"] { grid-column: 1 / -1; }
      .actions { grid-column: 1 / -1; align-items: flex-start; }
      .account-admin { grid-template-columns: 1fr; }
      .admin-actions { justify-content: flex-start; }
    }
  `
})
export class AccountsAdminComponent implements OnInit, OnChanges {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);

  @Input() refreshVersion = 0;
  readonly changed = output<void>();
  readonly sourceShort = SOURCE_SHORT;
  readonly benefits = signal<PlatformBenefit[]>([]);
  readonly accounts = signal<PlatformAccount[]>([]);
  readonly loadingAccounts = signal(true);
  readonly busyId = signal<number | null>(null);
  readonly grantingId = signal<number | null>(null);

  readonly grantableBenefits = computed(() =>
    this.benefits().filter((benefit) => benefit.active && benefit.combinationActive)
  );



  query = '';
  grantBenefitId: number | null = null;

  async ngOnInit(): Promise<void> {
    await Promise.all([this.loadBenefits(), this.loadAccounts()]);
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['refreshVersion'] && !changes['refreshVersion'].firstChange) {
      void Promise.all([this.loadBenefits(), this.loadAccounts()]);
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
      this.changed.emit();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busyId.set(null);
    }
  }

  daysLeft(iso: string): string {
    const ms = new Date(iso).getTime() - Date.now();
    if (ms <= 0) return 'vencido';
    const hours = Math.ceil(ms / 3_600_000);
    if (hours < 24) return `quedan ${hours} h`;
    const days = Math.ceil(hours / 24);
    return days === 1 ? 'queda 1 día' : `quedan ${days} días`;
  }

  private replace(updated: PlatformAccount): void {
    this.accounts.update((list) => list.map((account) =>
      account.id === updated.id ? updated : account
    ));
  }

  private async afterChange(account: PlatformAccount): Promise<void> {
    await this.loadBenefits();
    if (account.id === this.auth.me()?.account.id) {
      await this.auth.refreshMe();
    }
  }
}
