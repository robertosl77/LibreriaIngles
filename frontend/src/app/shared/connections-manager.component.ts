import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { AiConnection, ConnectionScope, ProviderInfo } from '../core/models';
import { ToastService } from '../core/toast.service';

const STATUS_TEXT: Record<string, string> = {
  AVAILABLE: 'Disponible',
  QUOTA_EXCEEDED: 'Sin cuota',
  RATE_LIMITED: 'Límite temporal',
  INVALID_CREDENTIALS: 'Credencial inválida',
  PROVIDER_DOWN: 'Proveedor caído',
  NETWORK_ERROR: 'Error de red',
  UNKNOWN_ERROR: 'Error',
  DISABLED: 'Deshabilitada'
};

interface NewConnection {
  provider: string;
  name: string;
  model: string;
  apiKey: string;
  priority: number;
  dailyRequestLimit: number | null;
  perAccountDailyLimit: number | null;
}

type LimitField = 'dailyRequestLimit' | 'perAccountDailyLimit';

/** Lista + alta de conexiones de IA. scope=account (BYOK) o scope=platform (PLATFORM_OWNER). */
@Component({
  selector: 'app-connections-manager',
  imports: [FormsModule, DatePipe],
  template: `
    <section class="card">
      <h2>{{ title() }}</h2>
      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else if (connections().length === 0) {
        <p class="muted">No hay conexiones todavía. Agregá una abajo.</p>
      } @else {
        <ul class="list">
          @for (c of connections(); track c.id) {
            <li class="list-item conn">
              <div class="conn-main">
                <div class="row">
                  <strong>{{ c.name }}</strong>
                  <span [class]="chip(c)">{{ statusText[c.status] || c.status }}</span>
                  @if (!c.active) { <span class="chip">Pausada</span> }
                  @if (limitReached(c)) { <span class="chip chip-warn">Límite 24 h alcanzado</span> }
                </div>
                <span class="muted small">
                  {{ providerLabel(c.provider) }} · {{ c.model }}
                  @if (c.credentialHint) { · {{ c.credentialHint }} }
                  @if (c.lastUsedAt) { · usada {{ c.lastUsedAt | date: 'dd/MM HH:mm' }} }
                  @if (c.backoffUntil && !c.usable) { · reintento {{ c.backoffUntil | date: 'HH:mm' }} }
                </span>
                @if (isPlatform()) {
                  <div class="limits">
                    <span class="small">
                      Uso 24 h: <strong>{{ c.usage24h ?? 0 }}</strong>
                      @if (c.dailyRequestLimit) { / {{ c.dailyRequestLimit }} }
                    </span>
                    @if (c.dailyRequestLimit) {
                      <div class="bar usage-bar" [attr.aria-label]="'Uso ' + (c.usage24h ?? 0) + ' de ' + c.dailyRequestLimit">
                        <span [style.width.%]="usagePercent(c)"></span>
                      </div>
                    }
                    <label class="small limit-field">
                      Límite total 24 h
                      <input class="input" type="number" min="1" placeholder="sin límite"
                        [ngModel]="c.dailyRequestLimit"
                        (change)="updateLimit(c, 'dailyRequestLimit', $any($event.target).value)" />
                    </label>
                    <label class="small limit-field">
                      Límite por usuario 24 h
                      <input class="input" type="number" min="1" placeholder="sin límite"
                        [ngModel]="c.perAccountDailyLimit"
                        (change)="updateLimit(c, 'perAccountDailyLimit', $any($event.target).value)" />
                    </label>
                  </div>
                }
              </div>
              <div class="row conn-actions">
                <label class="small prio">
                  Prioridad
                  <input class="input" type="number" min="1" [ngModel]="c.priority"
                    (change)="updatePriority(c, $any($event.target).value)" />
                </label>
                <button class="btn btn-sm" type="button" (click)="test(c)" [disabled]="busyId() === c.id">
                  @if (busyId() === c.id) { <span class="spinner"></span> } Probar
                </button>
                <button class="btn btn-sm" type="button" (click)="toggle(c)">{{ c.active ? 'Pausar' : 'Activar' }}</button>
                <button class="btn btn-sm btn-danger" type="button" (click)="remove(c)">Eliminar</button>
              </div>
            </li>
          }
        </ul>
      }
    </section>

    <section class="card">
      <h2>Agregar conexión</h2>
      <form class="stack" (ngSubmit)="create()">
        <div class="grid">
          <label class="field">
            Proveedor
            <select class="input" name="provider" [(ngModel)]="form.provider" (ngModelChange)="onProvider($event)">
              @for (p of providers(); track p.key) {
                <option [value]="p.key">{{ p.label }}</option>
              }
            </select>
          </label>
          <label class="field">
            Nombre
            <input class="input" name="name" [(ngModel)]="form.name" placeholder="Ej: OpenAI principal" required />
          </label>
          <label class="field">
            Modelo
            <input class="input" name="model" [(ngModel)]="form.model" [placeholder]="selectedProvider()?.defaultModel || ''" />
          </label>
          <label class="field">
            Prioridad
            <input class="input" type="number" min="1" name="priority" [(ngModel)]="form.priority" />
          </label>
          @if (isPlatform()) {
            <label class="field">
              Límite total 24 h
              <input class="input" type="number" min="1" name="daily" [(ngModel)]="form.dailyRequestLimit" placeholder="sin límite" />
            </label>
            <label class="field">
              Límite por usuario 24 h
              <input class="input" type="number" min="1" name="perAccount" [(ngModel)]="form.perAccountDailyLimit" placeholder="sin límite" />
            </label>
          }
        </div>
        @if (selectedProvider()?.requiresKey !== false) {
          <label class="field">
            API key
            <input class="input" type="password" name="apiKey" [(ngModel)]="form.apiKey" autocomplete="off" required />
          </label>
        }
        <div class="row">
          <button class="btn btn-primary" type="submit"
            [disabled]="creating() || !form.name || (selectedProvider()?.requiresKey !== false && !form.apiKey)">
            @if (creating()) { <span class="spinner"></span> Probando… } @else { Guardar y probar }
          </button>
        </div>
      </form>
    </section>
  `,
  styles: `
    :host { display: contents; }
    .conn { align-items: flex-start; flex-wrap: wrap; }
    .conn-main { display: flex; flex-direction: column; gap: 0.35rem; flex: 1; min-width: 240px; }
    .conn-actions { justify-content: flex-end; }
    .prio { display: flex; align-items: center; gap: 0.4rem; }
    .prio .input { width: 4.5rem; padding: 0.35rem 0.5rem; }
    .limits { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1rem; margin-top: 0.3rem; }
    .usage-bar { width: 120px; }
    .limit-field { display: flex; align-items: center; gap: 0.4rem; }
    .limit-field .input { width: 6.5rem; padding: 0.35rem 0.5rem; }
  `
})
export class ConnectionsManagerComponent implements OnInit {
  readonly scope = input<ConnectionScope>('account');
  readonly title = input('Tus conexiones');
  readonly changed = output<void>();

  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);

  readonly statusText = STATUS_TEXT;
  readonly providers = signal<ProviderInfo[]>([]);
  readonly connections = signal<AiConnection[]>([]);
  readonly loading = signal(true);
  readonly creating = signal(false);
  readonly busyId = signal<number | null>(null);
  readonly selectedProviderKey = signal('');
  readonly selectedProvider = computed(() =>
    this.providers().find((p) => p.key === this.selectedProviderKey())
  );
  readonly isPlatform = computed(() => this.scope() === 'platform');

  form: NewConnection = {
    provider: '',
    name: '',
    model: '',
    apiKey: '',
    priority: 1,
    dailyRequestLimit: null,
    perAccountDailyLimit: null
  };

  async ngOnInit(): Promise<void> {
    try {
      const providers = await firstValueFrom(this.api.providers());
      this.providers.set(providers);
      if (providers.length) {
        this.onProvider(providers[0].key);
      }
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
    await this.reload();
  }

  providerLabel(key: string): string {
    return this.providers().find((p) => p.key === key)?.label ?? key;
  }

  chip(c: AiConnection): string {
    if (!c.active) {
      return 'chip';
    }
    if (c.status === 'AVAILABLE') {
      return 'chip chip-ok';
    }
    return c.usable ? 'chip chip-warn' : 'chip chip-bad';
  }

  limitReached(c: AiConnection): boolean {
    return !!c.dailyRequestLimit && (c.usage24h ?? 0) >= c.dailyRequestLimit;
  }

  usagePercent(c: AiConnection): number {
    if (!c.dailyRequestLimit) {
      return 0;
    }
    return Math.min(100, Math.round(((c.usage24h ?? 0) / c.dailyRequestLimit) * 100));
  }

  onProvider(key: string): void {
    this.form.provider = key;
    this.selectedProviderKey.set(key);
    const info = this.providers().find((p) => p.key === key);
    if (info && (!this.form.name || this.providers().some((p) => p.label === this.form.name))) {
      this.form.name = info.label;
    }
  }

  private async reload(): Promise<void> {
    this.loading.set(true);
    try {
      const list = await firstValueFrom(this.api.connections(this.scope()));
      this.connections.set(list);
      this.form.priority = list.length ? Math.max(...list.map((c) => c.priority)) + 1 : 1;
      await this.auth.refreshMe();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  private async afterChange(): Promise<void> {
    await this.reload();
    this.changed.emit();
  }

  async create(): Promise<void> {
    this.creating.set(true);
    try {
      const created = await firstValueFrom(
        this.api.createConnection({
          provider: this.form.provider,
          name: this.form.name.trim(),
          model: this.form.model.trim() || null,
          apiKey: this.form.apiKey.trim() || null,
          priority: Number(this.form.priority) || 1,
          scope: this.scope(),
          ...(this.isPlatform()
            ? {
                dailyRequestLimit: this.toLimit(this.form.dailyRequestLimit),
                perAccountDailyLimit: this.toLimit(this.form.perAccountDailyLimit)
              }
            : {})
        })
      );
      this.report(created);
      this.form.apiKey = '';
      this.form.model = '';
      this.form.dailyRequestLimit = null;
      this.form.perAccountDailyLimit = null;
      await this.afterChange();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.creating.set(false);
    }
  }

  async test(c: AiConnection): Promise<void> {
    this.busyId.set(c.id);
    try {
      this.report(await firstValueFrom(this.api.testConnection(c.id)));
      await this.afterChange();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.busyId.set(null);
    }
  }

  async toggle(c: AiConnection): Promise<void> {
    await this.patch(c, { active: !c.active });
  }

  async updatePriority(c: AiConnection, value: string): Promise<void> {
    const priority = Number(value);
    if (Number.isFinite(priority) && priority >= 1 && priority !== c.priority) {
      await this.patch(c, { priority });
    }
  }

  async updateLimit(c: AiConnection, field: LimitField, value: string): Promise<void> {
    const limit = this.toLimit(value);
    if (limit !== c[field]) {
      await this.patch(c, { [field]: limit });
      this.toast.show(limit ? `Límite actualizado a ${limit}.` : 'Límite quitado.');
    }
  }

  async remove(c: AiConnection): Promise<void> {
    try {
      await firstValueFrom(this.api.deleteConnection(c.id));
      this.toast.show(`Conexión "${c.name}" eliminada.`);
      await this.afterChange();
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }

  private toLimit(value: unknown): number | null {
    const number = Number(value);
    return value === null || value === '' || !Number.isFinite(number) || number < 1
      ? null
      : Math.floor(number);
  }

  private async patch(
    c: AiConnection,
    body: Partial<{ active: boolean; priority: number; dailyRequestLimit: number | null; perAccountDailyLimit: number | null }>
  ): Promise<void> {
    try {
      await firstValueFrom(this.api.updateConnection(c.id, body));
      await this.afterChange();
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }

  private report(c: AiConnection): void {
    if (c.test?.ok) {
      this.toast.success(`"${c.name}" responde correctamente.`);
    } else if (c.test) {
      this.toast.error(`"${c.name}": ${c.test.error ?? 'no respondió'}`);
    }
  }
}
