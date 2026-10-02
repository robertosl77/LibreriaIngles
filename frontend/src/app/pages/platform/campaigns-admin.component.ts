import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import {
  CampaignNotification,
  CampaignRule,
  CampaignTrigger,
  PlatformCampaign,
  PlatformCampaignDraft,
  PlatformService
} from '../../core/models';
import { ToastService } from '../../core/toast.service';

interface CampaignForm {
  name: string;
  serviceId: number | null;
  trigger: CampaignTrigger;
  rules: CampaignRule[];
  grantDays: number | null;
  priority: number;
  stackable: boolean;
  maxRecipients: number | null;
  startsAt: string;
  endsAt: string;
  notification: CampaignNotification;
  message: string;
}

function defaultRules(): CampaignRule[] {
  return [
    { field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' },
    { field: 'HAS_GRANTED_SERVICE', operator: 'EQ', value: false }
  ];
}

function emptyForm(serviceId: number | null): CampaignForm {
  return {
    name: '',
    serviceId,
    trigger: 'FIRST_LOGIN',
    rules: defaultRules(),
    grantDays: 3,
    priority: 100,
    stackable: false,
    maxRecipients: null,
    startsAt: '',
    endsAt: '',
    notification: 'IN_APP',
    message: ''
  };
}

function numberOrNull(value: unknown): number | null {
  const n = Number(value);
  return value === null || value === '' || !Number.isFinite(n) || n <= 0 ? null : Math.round(n);
}

function localDate(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function isoDate(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

@Component({
  selector: 'app-campaigns-admin',
  imports: [FormsModule],
  template: `
    <section class="card stack">
      <div class="section-head">
        <div>
          <h2>Campañas</h2>
          <p class="muted small">
            Regla = cuándo evaluar + condiciones + beneficio + notificación + límites. Una persona
            recibe cada campaña una sola vez.
          </p>
        </div>
        @if (editingId() === null) {
          <button class="btn btn-sm" type="button" (click)="startNew()">Nueva campaña</button>
        }
      </div>

      @if (editingId() !== null) {
        <form class="editor stack" (ngSubmit)="save()">
          <div class="grid">
            <label class="field">
              Nombre
              <input class="input" name="cName" [(ngModel)]="form.name" maxlength="120" required />
            </label>
            <label class="field">
              Servicio que otorga
              <select class="input" name="cService" [(ngModel)]="form.serviceId" required>
                @for (service of grantableServices(); track service.id) {
                  <option [ngValue]="service.id">{{ service.name }}</option>
                }
              </select>
            </label>
            <label class="field">
              Cuándo se evalúa
              <select class="input" name="cTrigger" [(ngModel)]="form.trigger">
                <option value="FIRST_LOGIN">Primer login</option>
                <option value="LOGIN">Cada login</option>
                <option value="SCHEDULED" disabled>Programada / batch (T-059)</option>
              </select>
            </label>
            <label class="field">
              Días que otorga
              <input class="input" type="number" min="1" name="cDays" [(ngModel)]="form.grantDays"
                placeholder="duración del servicio" />
            </label>
            <label class="field">
              Prioridad
              <input class="input" type="number" min="1" name="cPriority" [(ngModel)]="form.priority" />
              <span class="muted tiny">1 = mayor prioridad. Puede repetirse.</span>
            </label>
            <label class="field">
              Máximo de beneficiarios
              <input class="input" type="number" min="1" name="cMax" [(ngModel)]="form.maxRecipients"
                placeholder="sin límite" />
            </label>
            <label class="field">
              Activa desde
              <input class="input" type="datetime-local" name="cStart" [(ngModel)]="form.startsAt" />
            </label>
            <label class="field">
              Activa hasta
              <input class="input" type="datetime-local" name="cEnd" [(ngModel)]="form.endsAt" />
            </label>
          </div>

          <div class="rules stack">
            <div class="row spread">
              <div>
                <strong>Condiciones</strong>
                <div class="muted tiny">Por ahora se cumplen TODAS (AND). El modelo queda preparado para grupos futuros.</div>
              </div>
              <button class="btn btn-sm" type="button" (click)="addRule()">+ Condición</button>
            </div>
            @if (form.rules.length === 0) {
              <p class="muted small">Sin condiciones adicionales: alcanza con el disparador y la vigencia.</p>
            }
            @for (rule of form.rules; track $index; let i = $index) {
              <div class="rule-row">
                <select class="input" [name]="'rField' + i" [(ngModel)]="rule.field" (ngModelChange)="resetRule(rule)">
                  <option value="ACCOUNT_TYPE">Tipo de cuenta</option>
                  <option value="HAS_GRANTED_SERVICE">Tiene servicio otorgado</option>
                  <option value="SERVICE_SOURCE">Fuente de IA actual</option>
                  <option value="EMAIL_DOMAIN">Dominio de email</option>
                  <option value="DAYS_SINCE_CREATED">Días desde registro</option>
                  <option value="CREATED_AT">Fecha de registro</option>
                </select>

                @if (rule.field === 'DAYS_SINCE_CREATED') {
                  <select class="input op" [name]="'rOp' + i" [(ngModel)]="rule.operator">
                    <option value="GTE">al menos</option>
                    <option value="LTE">como máximo</option>
                    <option value="EQ">exactamente</option>
                  </select>
                  <input class="input value" type="number" min="0" [name]="'rValue' + i" [(ngModel)]="rule.value" />
                } @else {
                  <span class="operator">es</span>
                  @switch (rule.field) {
                    @case ('ACCOUNT_TYPE') {
                      <select class="input value" [name]="'rValue' + i" [(ngModel)]="rule.value">
                        <option value="PERSONAL">Personal</option>
                        <option value="CORPORATE">Corporativa</option>
                      </select>
                    }
                    @case ('HAS_GRANTED_SERVICE') {
                      <select class="input value" [name]="'rValue' + i" [(ngModel)]="rule.value">
                        <option [ngValue]="false">No</option>
                        <option [ngValue]="true">Sí</option>
                      </select>
                    }
                    @case ('SERVICE_SOURCE') {
                      <select class="input value" [name]="'rValue' + i" [(ngModel)]="rule.value">
                        <option value="BYOK">Propias keys</option>
                        <option value="PLATFORM">Plataforma</option>
                        <option value="HYBRID">Híbrido</option>
                      </select>
                    }
                    @case ('CREATED_AT') {
                      <input class="input value" type="datetime-local" [name]="'rValue' + i" [(ngModel)]="rule.value" />
                    }
                    @default {
                      <input class="input value" [name]="'rValue' + i" [(ngModel)]="rule.value" placeholder="empresa.com" />
                    }
                  }
                }
                <button class="btn btn-sm btn-danger" type="button" (click)="removeRule(i)">Quitar</button>
              </div>
            }
          </div>

          <div class="grid">
            <label class="field">
              Notificación
              <select class="input" name="cNotification" [(ngModel)]="form.notification">
                <option value="NONE">Sin notificación</option>
                <option value="IN_APP">En pantalla</option>
                <option value="EMAIL">Email (queda pendiente hasta T-051)</option>
                <option value="IN_APP_EMAIL">Pantalla + email (email pendiente hasta T-051)</option>
              </select>
            </label>
            <label class="field">
              Mensaje
              <input class="input" name="cMessage" [(ngModel)]="form.message" maxlength="500"
                placeholder="Se genera uno automático si queda vacío" />
            </label>
          </div>

          <label class="check-row small">
            <input type="checkbox" name="cStack" [(ngModel)]="form.stackable" />
            Acumulable con otras campañas. Para combinar dos beneficios, ambas deben permitir acumulación.
          </label>

          <div class="row">
            <button class="btn btn-primary btn-sm" type="submit" [disabled]="saving() || !canSave()">
              @if (saving()) { <span class="spinner"></span> } Guardar
            </button>
            <button class="btn btn-sm" type="button" (click)="editingId.set(null)">Cancelar</button>
          </div>
        </form>
      }

      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else if (campaigns().length === 0) {
        <p class="muted">Todavía no hay campañas.</p>
      } @else {
        <div class="campaign-list">
          @for (campaign of campaigns(); track campaign.id) {
            <article class="campaign" [class.dim]="campaign.status === 'ENDED'">
              <div class="campaign-main">
                <div class="row">
                  <strong>{{ campaign.name }}</strong>
                  <span [class]="statusClass(campaign.status)">{{ statusLabel(campaign.status) }}</span>
                  <span class="chip">P{{ campaign.priority }}</span>
                  @if (campaign.stackable) { <span class="chip chip-ok">Acumulable</span> }
                </div>
                <div class="small">
                  {{ triggerLabel(campaign.trigger) }} → <strong>{{ campaign.serviceName }}</strong>
                  · {{ campaign.grantDays ? campaign.grantDays + ' días' : 'duración del servicio' }}
                  · {{ campaign.recipients }} beneficiario(s)
                  @if (campaign.maxRecipients) { / {{ campaign.maxRecipients }} máx. }
                </div>
                <div class="muted small">
                  {{ campaign.rules.length }} condición(es) · {{ notificationLabel(campaign.notification) }}
                  @if (campaign.pendingEmails) { · {{ campaign.pendingEmails }} email(s) pendientes }
                </div>
                @if (campaign.overlapWarnings.length) {
                  <div class="warning small">
                    Puede coincidir con
                    @for (warning of campaign.overlapWarnings; track warning.id; let last = $last) {
                      <strong>{{ warning.name }}</strong>{{ last ? '' : ', ' }}
                    }
                    . Revisá prioridad y acumulabilidad.
                  </div>
                }
              </div>
              <div class="actions row">
                @if (campaign.status !== 'ENDED') {
                  <button class="btn btn-sm" type="button" (click)="startEdit(campaign)">Editar</button>
                }
                @if (campaign.status === 'ACTIVE') {
                  <button class="btn btn-sm" type="button" (click)="changeStatus(campaign, 'pause')">Pausar</button>
                } @else if (campaign.status !== 'ENDED') {
                  <button class="btn btn-sm btn-primary" type="button" (click)="changeStatus(campaign, 'activate')">Activar</button>
                }
                @if (campaign.status !== 'ENDED') {
                  <button class="btn btn-sm btn-danger" type="button" (click)="finish(campaign)">Terminar</button>
                }
              </div>
            </article>
          }
        </div>
      }
    </section>
  `,
  styles: `
    :host { display: contents; }
    .section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
    .section-head h2, .section-head p { margin: 0; }
    .section-head p { margin-top: 0.3rem; }
    .editor, .rules { padding: 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; background: var(--bg); }
    .spread { justify-content: space-between; }
    .check-row { display: flex; gap: 0.5rem; align-items: flex-start; }
    .rule-row { display: grid; grid-template-columns: minmax(10rem, 1.4fr) minmax(6rem, 0.7fr) minmax(8rem, 1fr) auto; gap: 0.5rem; align-items: center; }
    .operator { text-align: center; font-size: 0.86rem; color: var(--muted); }
    .campaign-list { display: flex; flex-direction: column; gap: 0.55rem; }
    .campaign { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; padding: 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; }
    .campaign-main { display: flex; flex-direction: column; gap: 0.3rem; }
    .actions { flex: none; flex-wrap: wrap; justify-content: flex-end; }
    .warning { color: var(--warn); }
    .dim { opacity: 0.65; }
    .tiny { font-size: 0.76rem; }
    @media (max-width: 760px) {
      .rule-row { grid-template-columns: 1fr; }
      .operator { text-align: left; }
      .campaign { flex-direction: column; }
      .actions { justify-content: flex-start; }
    }
  `
})
export class CampaignsAdminComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly campaigns = signal<PlatformCampaign[]>([]);
  readonly services = signal<PlatformService[]>([]);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly editingId = signal<number | null>(null);
  readonly grantableServices = computed(() =>
    this.services().filter((service) => service.active && service.linkType === 'PERSONAL')
  );

  form: CampaignForm = emptyForm(null);

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const [campaigns, services] = await Promise.all([
        firstValueFrom(this.api.platformCampaigns()),
        firstValueFrom(this.api.platformServices())
      ]);
      this.campaigns.set(campaigns);
      this.services.set(services);
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  startNew(): void {
    this.form = emptyForm(this.grantableServices()[0]?.id ?? null);
    this.editingId.set(0);
  }

  startEdit(campaign: PlatformCampaign): void {
    this.form = {
      name: campaign.name,
      serviceId: campaign.serviceId,
      trigger: campaign.trigger,
      rules: campaign.rules.map((rule) => ({ ...rule })),
      grantDays: campaign.grantDays,
      priority: campaign.priority,
      stackable: campaign.stackable,
      maxRecipients: campaign.maxRecipients,
      startsAt: localDate(campaign.startsAt),
      endsAt: localDate(campaign.endsAt),
      notification: campaign.notification,
      message: campaign.message ?? ''
    };
    this.editingId.set(campaign.id);
  }

  addRule(): void {
    this.form.rules.push({ field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' });
  }

  removeRule(index: number): void {
    this.form.rules.splice(index, 1);
  }

  resetRule(rule: CampaignRule): void {
    rule.operator = 'EQ';
    if (rule.field === 'ACCOUNT_TYPE') rule.value = 'PERSONAL';
    else if (rule.field === 'HAS_GRANTED_SERVICE') rule.value = false;
    else if (rule.field === 'SERVICE_SOURCE') rule.value = 'BYOK';
    else if (rule.field === 'DAYS_SINCE_CREATED') rule.value = 0;
    else if (rule.field === 'CREATED_AT') rule.value = '';
    else rule.value = '';
  }

  canSave(): boolean {
    return !!this.form.name.trim() && !!this.form.serviceId && this.form.priority > 0;
  }

  async save(): Promise<void> {
    const id = this.editingId();
    if (id === null || !this.form.serviceId) return;
    const draft: PlatformCampaignDraft = {
      name: this.form.name.trim(),
      serviceId: this.form.serviceId,
      trigger: this.form.trigger,
      rules: this.form.rules.map((rule) => ({
        ...rule,
        value:
          rule.field === 'DAYS_SINCE_CREATED'
            ? Number(rule.value)
            : rule.field === 'CREATED_AT' && rule.value
              ? new Date(String(rule.value)).toISOString()
              : rule.value
      })),
      grantDays: numberOrNull(this.form.grantDays),
      priority: Math.max(1, Math.round(Number(this.form.priority) || 100)),
      stackable: this.form.stackable,
      maxRecipients: numberOrNull(this.form.maxRecipients),
      startsAt: isoDate(this.form.startsAt),
      endsAt: isoDate(this.form.endsAt),
      notification: this.form.notification,
      message: this.form.message.trim() || null
    };
    this.saving.set(true);
    try {
      await firstValueFrom(
        id ? this.api.updatePlatformCampaign(id, draft) : this.api.createPlatformCampaign(draft)
      );
      this.toast.success(id ? 'Campaña actualizada.' : 'Campaña creada en borrador.');
      this.editingId.set(null);
      await this.load();
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }

  async changeStatus(campaign: PlatformCampaign, action: 'activate' | 'pause'): Promise<void> {
    try {
      await firstValueFrom(
        action === 'activate'
          ? this.api.activatePlatformCampaign(campaign.id)
          : this.api.pausePlatformCampaign(campaign.id)
      );
      await this.load();
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }

  async finish(campaign: PlatformCampaign): Promise<void> {
    if (!confirm(`¿Terminar la campaña "${campaign.name}"? No volverá a ejecutarse.`)) return;
    try {
      await firstValueFrom(this.api.finishPlatformCampaign(campaign.id));
      await this.load();
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }

  triggerLabel(trigger: CampaignTrigger): string {
    return trigger === 'FIRST_LOGIN' ? 'Primer login' : trigger === 'LOGIN' ? 'Cada login' : 'Programada';
  }

  notificationLabel(notification: CampaignNotification): string {
    const labels: Record<CampaignNotification, string> = {
      NONE: 'sin notificación',
      IN_APP: 'pantalla',
      EMAIL: 'email',
      IN_APP_EMAIL: 'pantalla + email'
    };
    return labels[notification];
  }

  statusLabel(status: PlatformCampaign['status']): string {
    return { DRAFT: 'Borrador', ACTIVE: 'Activa', PAUSED: 'Pausada', ENDED: 'Terminada' }[status];
  }

  statusClass(status: PlatformCampaign['status']): string {
    return status === 'ACTIVE' ? 'chip chip-ok' : status === 'PAUSED' ? 'chip chip-warn' : 'chip';
  }
}
