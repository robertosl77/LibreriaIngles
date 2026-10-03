import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AiSource, PlatformAccount } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';

const SOURCE_SHORT: Record<AiSource, string> = {
  BYOK: 'Propias keys',
  PLATFORM: 'Plataforma',
  HYBRID: 'Híbrido'
};

@Component({
  selector: 'app-accounts-summary',
  imports: [DatePipe, CollapseCardComponent],
  template: `
    <app-collapse-card
      title="Cuentas"
      description="Vista informativa de las cuentas y la membresía efectiva que está usando cada una."
    >
      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else {
        <div class="membership-summary">
          @for (group of membershipGroups(); track group.source) {
            <article class="membership-card">
              <div>
                <strong>Personal</strong>
                <div class="muted small">{{ sourceShort[group.source] }}</div>
              </div>
              <strong class="count">{{ group.accounts.length }}</strong>
            </article>
          }
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cuenta</th>
                <th>Membresía</th>
                <th>Beneficio vigente</th>
                <th>Vence</th>
                <th>Actividad</th>
              </tr>
            </thead>
            <tbody>
              @for (account of regularAccounts(); track account.id) {
                <tr>
                  <td>{{ account.email }}</td>
                  <td>
                    {{ account.service.linkType === 'PERSONAL' ? 'Personal' : 'Corporativa' }}
                    · {{ sourceShort[account.service.source] }}
                  </td>
                  <td>{{ account.service.benefitName ?? 'Sin beneficio' }}</td>
                  <td>
                    @if (account.service.expiresAt) {
                      {{ account.service.expiresAt | date: 'dd/MM/yyyy HH:mm' }}
                    } @else {
                      —
                    }
                  </td>
                  <td>
                    {{ account.platformRequests24h }} {{ account.platformRequests24h === 1 ? 'pedido' : 'pedidos' }}
                    <div class="muted small">
                      en 24 h · {{ account.ownConnections }} {{ account.ownConnections === 1 ? 'key' : 'keys' }}
                    </div>
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

    .membership-summary {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.75rem;
      margin-bottom: 0.9rem;
    }

    .membership-card {
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: flex-start;
      padding: 0.8rem;
      border: 1px solid var(--border);
      border-radius: 0.6rem;
      background: var(--bg);
    }

    .count { font-size: 1.2rem; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    th, td {
      text-align: left;
      padding: 0.45rem 0.8rem 0.45rem 0;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }

    @media (max-width: 760px) {
      .membership-summary { grid-template-columns: 1fr; }
    }
  `
})
export class AccountsSummaryComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly sourceShort = SOURCE_SHORT;
  readonly accounts = signal<PlatformAccount[]>([]);
  readonly loading = signal(true);

  readonly regularAccounts = computed(() =>
    this.accounts().filter((account) => !account.isPlatformOwner)
  );

  readonly membershipGroups = computed(() =>
    (['BYOK', 'PLATFORM', 'HYBRID'] as AiSource[]).map((source) => ({
      source,
      accounts: this.regularAccounts().filter(
        (account) => account.service.linkType === 'PERSONAL' && account.service.source === source
      )
    }))
  );

  async ngOnInit(): Promise<void> {
    try {
      this.accounts.set(await firstValueFrom(this.api.platformAccounts('')));
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }
}
