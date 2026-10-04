import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../core/api.service';
import { AuthService } from '../core/auth.service';
import { AiConnection, ConnectionScope, ModelOption, ProviderInfo } from '../core/models';
import { ToastService } from '../core/toast.service';
import { ModelPickerComponent } from './model-picker.component';

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
  imports: [FormsModule, DatePipe, ModelPickerComponent],
  template: `
    <section [class.card]="!embedded()" class="manager-shell">
      @if (!embedded()) {
        <h2>{{ title() }}</h2>
        @if (note()) { <p class="muted small note">{{ note() }}</p> }
      }
      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else if (connections().length === 0) {
        <p class="muted">No hay conexiones todavía. Agregá una abajo.</p>
      } @else {
        <ul class="list">
          @for (c of connections(); track c.id) {
            <li class="list-item conn" [class.focused]="focusConnectionId() === c.id" [attr.id]="'ai-connection-' + c.id">
              <div class="conn-main">
                <div class="row">
                  <strong>{{ c.name }}</strong>
                  <span [class]="chip(c)">{{ statusText[c.status] || c.status }}</span>
                  @if (!c.active) { <span class="chip">Pausada</span> }
                  @if (limitReached(c)) { <span class="chip chip-warn">Límite 24 h alcanzado</span> }
                </div>
                <span class="muted small">
                  {{ providerLabel(c.provider) }} · {{ c.model }}
                  @if (c.lastUsedAt) { · usada {{ c.lastUsedAt | date: 'dd/MM HH:mm' }} }
                  @if (c.backoffUntil && !c.usable) { · reintento {{ c.backoffUntil | date: 'HH:mm' }} }
                </span>
                @if (c.credentialHint) {
                  <div class="credential-row small">
                    <span class="muted">API key:</span>
                    <code class="secret-value">{{ c.credentialHint }}</code>
                    @if (isOwner()) {
                      <button
                        class="copy-key-btn"
                        type="button"
                        (click)="copyKey(c)"
                        [disabled]="credentialBusyId() === c.id"
                        [attr.aria-label]="'Copiar API key de ' + c.name"
                        [attr.title]="'Copiar API key de ' + c.name"
                      >
                        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                          <rect x="9" y="9" width="10" height="10" rx="1.5"></rect>
                          <path d="M15 9V6.5A1.5 1.5 0 0 0 13.5 5h-8A1.5 1.5 0 0 0 4 6.5v8A1.5 1.5 0 0 0 5.5 16H9"></path>
                        </svg>
                      </button>
                    }
                  </div>
                }
                @if (isPlatform()) {
                  <div class="limits">
                    <span class="small">
                      Uso 24 h (pedidos): <strong>{{ c.usage24h ?? 0 }}</strong>
                      @if (c.dailyRequestLimit) { / {{ c.dailyRequestLimit }} }
                    </span>
                    @if (c.dailyRequestLimit) {
                      <div class="bar usage-bar" [attr.aria-label]="'Uso de pedidos ' + (c.usage24h ?? 0) + ' de ' + c.dailyRequestLimit">
                        <span [style.width.%]="usagePercent(c)"></span>
                      </div>
                    }
                    <label class="small limit-field">
                      Límite total 24 h (pedidos)
                      <input class="input" type="number" min="1" placeholder="sin límite"
                        [ngModel]="c.dailyRequestLimit"
                        (change)="updateLimit(c, 'dailyRequestLimit', $any($event.target).value)" />
                    </label>
                    <label class="small limit-field">
                      Límite por usuario 24 h (pedidos)
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
                <button class="btn btn-sm" type="button" (click)="startEdit(c)" [disabled]="editingId() === c.id">Editar</button>
                <button class="btn btn-sm" type="button" (click)="toggle(c)">{{ c.active ? 'Pausar' : 'Activar' }}</button>
                <button class="btn btn-sm btn-danger" type="button" (click)="remove(c)">Eliminar</button>
              </div>
              @if (editingId() === c.id) {
                <form class="edit stack" (ngSubmit)="saveEdit(c)">
                  <div class="grid">
                    <label class="field">
                      Nombre
                      <input class="input" name="editName" [(ngModel)]="edit.name" required />
                    </label>
                    <div class="field">
                      Proveedor
                      <span class="input readonly">{{ providerLabel(c.provider) }}</span>
                      <span class="small muted">No se puede cambiar: para otro proveedor, creá otra conexión.</span>
                    </div>
                  </div>
                  <div class="field">
                    Modelo
                    <app-model-picker name="editModel" [(value)]="edit.model" [options]="editModels()"
                      [loading]="editModelsLoading()" [error]="editModelsError()" (refresh)="loadEditModels(c)" />
                  </div>
                  @if (requiresKey(c.provider)) {
                    <label class="field">
                      Nueva API key
                      <input class="input" type="password" name="editKey" [(ngModel)]="edit.apiKey" autocomplete="off"
                        placeholder="Dejar vacío para mantener la actual ({{ c.credentialHint }})"
                        (change)="edit.apiKey && loadEditModels(c)" />
                    </label>
                  }
                  <div class="row">
                    <button class="btn btn-primary btn-sm" type="submit" [disabled]="saving() || !edit.name.trim() || !edit.model.trim()">
                      @if (saving()) { <span class="spinner"></span> Guardando… } @else { Guardar y probar }
                    </button>
                    <button class="btn btn-sm" type="button" (click)="cancelEdit()">Cancelar</button>
                  </div>
                </form>
              }
            </li>
          }
        </ul>
      }
    </section>

    @if (allowCreate()) {
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
            Prioridad
            <input class="input" type="number" min="1" name="priority" [(ngModel)]="form.priority" />
          </label>
          @if (isPlatform()) {
            <label class="field">
              Límite total 24 h (pedidos)
              <input class="input" type="number" min="1" name="daily" [(ngModel)]="form.dailyRequestLimit" placeholder="sin límite" />
            </label>
            <label class="field">
              Límite por usuario 24 h (pedidos)
              <input class="input" type="number" min="1" name="perAccount" [(ngModel)]="form.perAccountDailyLimit" placeholder="sin límite" />
            </label>
          }
        </div>
        @if (selectedProvider()?.requiresKey !== false) {
          <label class="field">
            API key
            <input class="input" type="password" name="apiKey" [(ngModel)]="form.apiKey" autocomplete="off" required
              (change)="loadNewModels()" />
          </label>
        }
        <div class="field">
          Modelo
          <app-model-picker name="model" [(value)]="form.model" [options]="newModels()"
            [loading]="newModelsLoading()" [error]="newModelsError()"
            [placeholder]="selectedProvider()?.defaultModel || ''"
            [canRefresh]="selectedProvider()?.requiresKey === false || !!form.apiKey"
            hint="Pegá la API key y se cargan los modelos disponibles en tu cuenta."
            (refresh)="loadNewModels()" />
        </div>
        <div class="row">
          <button class="btn btn-primary" type="submit"
            [disabled]="creating() || !form.name || (selectedProvider()?.requiresKey !== false && !form.apiKey)">
            @if (creating()) { <span class="spinner"></span> Probando… } @else { Guardar y probar }
          </button>
        </div>
      </form>
    </section>
    }
  `,
  styles: `
    :host { display: contents; }
    .note { margin: -0.4rem 0 0.8rem; }
    .conn { align-items: flex-start; flex-wrap: wrap; }
    .conn.focused { outline: 2px solid var(--accent); outline-offset: -2px; }
    .conn-main { display: flex; flex-direction: column; gap: 0.35rem; flex: 1; min-width: 240px; }
    .conn-actions { justify-content: flex-end; }
    .prio { display: flex; align-items: center; gap: 0.4rem; }
    .prio .input { width: 4.5rem; padding: 0.35rem 0.5rem; }
    .limits { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 1rem; margin-top: 0.3rem; }
    .credential-row { display: flex; align-items: center; gap: 0.3rem; flex-wrap: wrap; }
    .secret-value {
      max-width: min(100%, 36rem); overflow-wrap: anywhere; user-select: text;
      padding: 0.2rem 0.35rem; border-radius: 0.35rem; background: var(--bg);
    }
    .copy-key-btn {
      width: 1.75rem; height: 1.75rem; padding: 0; border: 0; border-radius: 0.35rem;
      display: inline-flex; align-items: center; justify-content: center;
      background: transparent; color: var(--muted); cursor: pointer;
    }
    .copy-key-btn:hover:not(:disabled) { background: var(--bg); color: var(--text); }
    .copy-key-btn:disabled { opacity: 0.45; cursor: wait; }
    .copy-key-btn svg { fill: none; stroke: currentColor; stroke-width: 1.6; }
    .usage-bar { width: 120px; }
    .limit-field { display: flex; align-items: center; gap: 0.4rem; }
    .limit-field .input { width: 6.5rem; padding: 0.35rem 0.5rem; }
    .edit { flex-basis: 100%; border-top: 1px dashed var(--border); padding-top: 0.9rem; margin-top: 0.3rem; }
    .readonly { background: var(--bg); color: var(--muted); }
  `
})
export class ConnectionsManagerComponent implements OnInit {
  readonly scope = input<ConnectionScope>('account');
  readonly title = input('Tus conexiones');
  /** false: solo se administran las existentes (ej. servicio Plataforma, T-055). */
  readonly allowCreate = input(true);
  readonly note = input<string | null>(null);
  /** true: el contenedor visual/título lo provee una tarjeta compartida externa. */
  readonly embedded = input(false);
  /** Conexión a resaltar al llegar desde Consumo. */
  readonly focusConnectionId = input<number | null>(null);
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
  readonly isOwner = computed(() => this.auth.me()?.account.isPlatformOwner ?? false);
  readonly credentialBusyId = signal<number | null>(null);

  // Modelos disponibles (consultados al proveedor)
  readonly newModels = signal<ModelOption[] | null>(null);
  readonly newModelsLoading = signal(false);
  readonly newModelsError = signal<string | null>(null);
  readonly editingId = signal<number | null>(null);
  readonly editModels = signal<ModelOption[] | null>(null);
  readonly editModelsLoading = signal(false);
  readonly editModelsError = signal<string | null>(null);
  readonly saving = signal(false);
  edit = { name: '', model: '', apiKey: '' };

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

  async copyKey(connection: AiConnection): Promise<void> {
    this.credentialBusyId.set(connection.id);
    try {
      const response = await firstValueFrom(
        this.api.copyConnectionCredential(connection.id)
      );
      await this.copyText(response.apiKey);
      this.toast.success(`API key de "${connection.name}" copiada.`);
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo copiar la API key.'));
    } finally {
      this.credentialBusyId.set(null);
    }
  }

  private async copyText(value: string): Promise<void> {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }

    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
      if (!document.execCommand('copy')) {
        throw new Error('Clipboard API no disponible.');
      }
    } finally {
      textarea.remove();
    }
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

  requiresKey(provider: string): boolean {
    return this.providers().find((p) => p.key === provider)?.requiresKey !== false;
  }

  /** Alta: consulta los modelos con la key recién pegada (no se guarda). */
  async loadNewModels(): Promise<void> {
    const provider = this.form.provider;
    const needsKey = this.requiresKey(provider);
    if (!provider || (needsKey && !this.form.apiKey.trim())) {
      return;
    }
    this.newModelsLoading.set(true);
    this.newModelsError.set(null);
    try {
      const models = await firstValueFrom(
        this.api.listModels(provider, needsKey ? this.form.apiKey.trim() : null)
      );
      if (provider !== this.form.provider) {
        return; // cambió el proveedor mientras se consultaba
      }
      this.newModels.set(models);
      if (!this.form.model || !models.some((m) => m.id === this.form.model)) {
        const fallback = this.selectedProvider()?.defaultModel;
        this.form.model = models.find((m) => m.id === fallback)?.id ?? models[0]?.id ?? '';
      }
    } catch (err) {
      this.newModels.set(null);
      this.newModelsError.set(errorMessage(err, 'No se pudo obtener la lista de modelos.'));
    } finally {
      this.newModelsLoading.set(false);
    }
  }

  startEdit(c: AiConnection): void {
    this.editingId.set(c.id);
    this.edit = { name: c.name, model: c.model, apiKey: '' };
    this.editModels.set(null);
    void this.loadEditModels(c);
  }

  cancelEdit(): void {
    this.editingId.set(null);
  }

  /** Edición: con la key nueva si se ingresó, o con la guardada. */
  async loadEditModels(c: AiConnection): Promise<void> {
    this.editModelsLoading.set(true);
    this.editModelsError.set(null);
    try {
      const request = this.edit.apiKey.trim()
        ? this.api.listModels(c.provider, this.edit.apiKey.trim())
        : this.api.connectionModels(c.id);
      this.editModels.set(await firstValueFrom(request));
    } catch (err) {
      this.editModels.set(null);
      this.editModelsError.set(errorMessage(err, 'No se pudo obtener la lista de modelos.'));
    } finally {
      this.editModelsLoading.set(false);
    }
  }

  async saveEdit(c: AiConnection): Promise<void> {
    const body: { name?: string; model?: string; apiKey?: string } = {};
    if (this.edit.name.trim() !== c.name) {
      body.name = this.edit.name.trim();
    }
    if (this.edit.model.trim() !== c.model) {
      body.model = this.edit.model.trim();
    }
    if (this.edit.apiKey.trim()) {
      body.apiKey = this.edit.apiKey.trim();
    }
    if (!Object.keys(body).length) {
      this.cancelEdit();
      return;
    }
    this.saving.set(true);
    try {
      const updated = await firstValueFrom(this.api.updateConnection(c.id, body));
      this.report(updated);
      if (!updated.test) {
        this.toast.success(`"${updated.name}" actualizada.`);
      }
      this.editingId.set(null);
      await this.afterChange();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }

  onProvider(key: string): void {
    this.form.provider = key;
    this.selectedProviderKey.set(key);
    this.form.model = '';
    this.form.apiKey = ''; // cada API key vale para un solo proveedor
    this.newModels.set(null);
    this.newModelsError.set(null);
    if (!this.requiresKey(key)) {
      void this.loadNewModels();
    }
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
      this.focusRequestedConnection();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  private focusRequestedConnection(): void {
    const id = this.focusConnectionId();
    if (id === null || !this.connections().some((connection) => connection.id === id)) {
      return;
    }
    setTimeout(() => {
      document.getElementById(`ai-connection-${id}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });
    });
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
      this.newModels.set(null);
      if (!this.requiresKey(this.form.provider)) {
        void this.loadNewModels();
      }
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
