import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { AiConnection, ConnectionScope, ProviderInfo } from '../../core/models';
import { ToastService } from '../../core/toast.service';

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
}

@Component({
  selector: 'app-ai-settings',
  imports: [FormsModule, DatePipe],
  template: `
    <main class="page stack">
      <div class="page-header">
        <div>
          <h1>Conexiones de IA</h1>
          <p class="muted">
            Se usan en orden de prioridad (1 = primero). Si una falla o se queda sin cuota, la app
            pasa sola a la siguiente. Las API keys se guardan cifradas y nunca vuelven al navegador.
          </p>
        </div>
      </div>

      @if (isOwner()) {
        <div class="row tabs" role="tablist">
          <button type="button" class="btn btn-sm" [class.btn-primary]="scope() === 'account'" (click)="setScope('account')">Mis conexiones</button>
          <button type="button" class="btn btn-sm" [class.btn-primary]="scope() === 'platform'" (click)="setScope('platform')">Plataforma (PLATFORM_OWNER)</button>
        </div>
        @if (scope() === 'platform') {
          <p class="banner banner-info small">
            Las conexiones de plataforma están disponibles para todos los usuarios, después de sus propias conexiones.
          </p>
        }
      }

      <section class="card">
        <h2>{{ scope() === 'platform' ? 'Conexiones de la plataforma' : 'Tus conexiones' }}</h2>
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
                  </div>
                  <span class="muted small">
                    {{ providerLabel(c.provider) }} · {{ c.model }}
                    @if (c.credentialHint) { · {{ c.credentialHint }} }
                    @if (c.lastUsedAt) { · usada {{ c.lastUsedAt | date: 'dd/MM HH:mm' }} }
                    @if (c.backoffUntil && !c.usable) { · reintento {{ c.backoffUntil | date: 'HH:mm' }} }
                  </span>
                </div>
                <div class="row conn-actions">
                  <label class="small prio">
                    Prioridad
                    <input
                      class="input"
                      type="number"
                      min="1"
                      [ngModel]="c.priority"
                      (change)="updatePriority(c, $any($event.target).value)"
                    />
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
          </div>
          @if (selectedProvider()?.requiresKey !== false) {
            <label class="field">
              API key
              <input class="input" type="password" name="apiKey" [(ngModel)]="form.apiKey" autocomplete="off" required />
            </label>
          }
          <div class="row">
            <button class="btn btn-primary" type="submit" [disabled]="creating() || !form.name || (selectedProvider()?.requiresKey !== false && !form.apiKey)">
              @if (creating()) { <span class="spinner"></span> Probando… } @else { Guardar y probar }
            </button>
          </div>
        </form>
      </section>
    </main>
  `,
  styles: `
    .conn { align-items: flex-start; flex-wrap: wrap; }
    .conn-main { display: flex; flex-direction: column; gap: 0.3rem; }
    .conn-actions { justify-content: flex-end; }
    .prio { display: flex; align-items: center; gap: 0.4rem; }
    .prio .input { width: 4.5rem; padding: 0.35rem 0.5rem; }
  `
})
export class AiSettingsComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);

  readonly statusText = STATUS_TEXT;
  readonly providers = signal<ProviderInfo[]>([]);
  readonly connections = signal<AiConnection[]>([]);
  readonly loading = signal(true);
  readonly creating = signal(false);
  readonly busyId = signal<number | null>(null);
  readonly scope = signal<ConnectionScope>('account');
  readonly isOwner = computed(() => this.auth.me()?.account.isPlatformOwner ?? false);
  readonly selectedProviderKey = signal('');
  readonly selectedProvider = computed(() =>
    this.providers().find((p) => p.key === this.selectedProviderKey())
  );

  form: NewConnection = { provider: '', name: '', model: '', apiKey: '', priority: 1 };

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

  onProvider(key: string): void {
    this.form.provider = key;
    this.selectedProviderKey.set(key);
    const info = this.providers().find((p) => p.key === key);
    if (info && (!this.form.name || this.providers().some((p) => p.label === this.form.name))) {
      this.form.name = info.label;
    }
  }

  async setScope(scope: ConnectionScope): Promise<void> {
    this.scope.set(scope);
    await this.reload();
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
          scope: this.scope()
        })
      );
      this.report(created);
      this.form.apiKey = '';
      this.form.model = '';
      await this.reload();
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
      await this.reload();
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

  async remove(c: AiConnection): Promise<void> {
    try {
      await firstValueFrom(this.api.deleteConnection(c.id));
      this.toast.show(`Conexión "${c.name}" eliminada.`);
      await this.reload();
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }

  private async patch(c: AiConnection, body: { active?: boolean; priority?: number }): Promise<void> {
    try {
      await firstValueFrom(this.api.updateConnection(c.id, body));
      await this.reload();
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
