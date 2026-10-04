import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import {
  CampaignAction,
  CampaignAssistRequirement,
  CampaignAudiencePreview,
  CampaignNotification,
  CampaignRule,
  CampaignRuleCapability,
  CampaignTrigger,
  PlatformCampaign,
  PlatformBenefit,
  PlatformCampaignCapabilities,
  PlatformCampaignDraft
} from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';
import { CAMPAIGN_TEMPLATES, CampaignTemplate } from './campaign-templates';

type NewCampaignMode = 'choose' | 'templates' | 'ai' | null;

interface CampaignForm {
  name: string;
  benefitId: number | null;
  action: CampaignAction;
  actionConfig: Record<string, unknown>;
  trigger: CampaignTrigger;
  rules: CampaignRule[];
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

function emptyForm(benefitId: number | null): CampaignForm {
  return {
    name: '',
    benefitId,
    action: 'GRANT_BENEFIT',
    actionConfig: {},
    trigger: 'FIRST_LOGIN',
    rules: defaultRules(),
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
  imports: [FormsModule, CollapseCardComponent],
  template: `
    <app-collapse-card
      title="Campañas"
      description="Definí qué hace la campaña, cuándo compite, a quién alcanza, cómo se entrega y durante qué vigencia. Cada persona recibe cada campaña una sola vez."
    >
      @if (editingId() === null && !newMode()) {
        <div class="collapse-actions">
          <button class="btn btn-sm" type="button" (click)="startNew()">Nueva campaña</button>
        </div>
      }

      @if (newMode()) {
        <section class="creator stack">
          <div class="row spread creator-head">
            <div>
              <strong>Nueva campaña</strong>
              <div class="muted small">Elegí cómo querés armar el borrador. Los tres caminos terminan en el mismo formulario.</div>
            </div>
            <button class="btn btn-sm" type="button" (click)="cancelNew()">Cancelar</button>
          </div>

          @if (newMode() === 'choose') {
            <div class="creation-options">
              <button class="choice-card" type="button" (click)="newMode.set('templates')">
                <strong>Usar plantilla</strong>
                <span>Partí de casos frecuentes ya configurados y ajustá los valores.</span>
              </button>
              <button class="choice-card" type="button" (click)="newMode.set('ai')">
                <strong>Describir con IA</strong>
                <span>Contá qué querés lograr y la IA arma un borrador revisable.</span>
              </button>
              <button class="choice-card" type="button" (click)="startManual()">
                <strong>Configurar manualmente</strong>
                <span>Usá directamente el constructor completo de campañas.</span>
              </button>
            </div>
          }

          @if (newMode() === 'templates') {
            <div class="row spread">
              <strong>Plantillas</strong>
              <button class="btn btn-sm" type="button" (click)="newMode.set('choose')">Volver</button>
            </div>
            <div class="template-grid">
              @for (template of templates; track template.id) {
                <button class="template-card" type="button" (click)="applyTemplate(template)">
                  <strong>{{ template.title }}</strong>
                  <span>{{ template.description }}</span>
                </button>
              }
            </div>
          }

          @if (newMode() === 'ai') {
            <div class="row spread">
              <strong>Describí la campaña</strong>
              <button class="btn btn-sm" type="button" (click)="newMode.set('choose')">Volver</button>
            </div>
            <label class="field">
              Qué querés lograr
              <textarea
                class="input ai-description"
                name="campaignAiDescription"
                [(ngModel)]="aiDescription"
                maxlength="2000"
                rows="4"
                placeholder="Ej. A quienes cumplen un año desde el registro, darles un beneficio de fidelización cuando vuelvan a ingresar."
              ></textarea>
            </label>
            <p class="muted tiny">
              La IA usa una conexión de la plataforma y genera únicamente un borrador con las capacidades actuales.
              Nunca guarda ni activa la campaña.
            </p>
            <div class="row">
              <button
                class="btn btn-primary btn-sm"
                type="button"
                (click)="generateWithAi()"
                [disabled]="aiLoading() || aiDescription.trim().length < 8"
              >
                @if (aiLoading()) { <span class="spinner"></span> }
                Interpretar con IA
              </button>
            </div>
          }
        </section>
      }

      @if (editingId() !== null) {
        @if (draftSummary()) {
          <div class="banner small draft-banner" [class.draft-blocked]="!aiDraftExecutable()">
            <strong>{{ draftSummary() }}</strong>
            @if (!aiDraftExecutable()) {
              <div class="warning"><strong>Borrador incompleto: no se puede guardar ni previsualizar.</strong></div>
              @for (issue of draftBlockingIssues(); track issue) {
                <div class="warning">· {{ issue }}</div>
              }
            }
            @for (warning of draftWarnings(); track warning) {
              <div>· {{ warning }}</div>
            }
            @if (draftRequirements().length) {
              <div class="requirement-list">
                @for (requirement of draftRequirements(); track requirement.text + requirement.kind) {
                  <div [class.warning]="!requirement.verified">
                    {{ requirement.verified ? '✓' : '!' }} {{ requirement.text }}
                  </div>
                }
              </div>
            }
          </div>
        }
        @if (capabilitiesError()) {
          <div class="banner small draft-banner">
            <strong>El constructor no puede cargar el catálogo del motor.</strong>
            <div>{{ capabilitiesError() }}</div>
          </div>
        }
        @if (capabilities()) {
        <form class="editor stack" (ngSubmit)="save()">
          <section class="editor-section stack">
            <div class="section-head">
              <div>
                <strong>1. Qué hace</strong>
                <div class="muted tiny">Identidad de la campaña y acción que ejecutará cuando corresponda.</div>
              </div>
            </div>
            <div class="grid">
              <label class="field">
                Nombre
                <input class="input" name="cName" [(ngModel)]="form.name" maxlength="120" required />
              </label>
              <label class="field">
                Acción
                <select class="input" name="cAction" [(ngModel)]="form.action">
                  @for (action of capabilities()?.actions ?? []; track action.key) {
                    <option [value]="action.key" [disabled]="!action.available">
                      {{ action.label }}{{ action.available ? '' : ' · próxima etapa' }}
                    </option>
                  }
                </select>
                <span class="muted tiny">Hoy se ejecuta Otorgar beneficio; las demás acciones quedan reservadas para etapas futuras.</span>
              </label>
              <label class="field">
                Beneficio que aplica
                <select class="input" name="cBenefit" [(ngModel)]="form.benefitId" required>
                  <option [ngValue]="null" disabled>Elegí un beneficio</option>
                  @for (benefit of activeBenefits(); track benefit.id) {
                    <option [ngValue]="benefit.id">{{ benefit.name }}</option>
                  }
                </select>
                <span class="muted tiny">La composición del beneficio se consulta y edita en Beneficios.</span>
              </label>
            </div>
          </section>

          <section class="editor-section stack">
            <div class="section-head">
              <div>
                <strong>2. Cuándo se evalúa y cómo compite</strong>
                <div class="muted tiny">Estas opciones resuelven campañas elegibles en la misma evaluación. No representan supresiones históricas ni frequency caps.</div>
              </div>
            </div>
            <div class="grid">
              <label class="field">
                Cuándo se evalúa
                <select class="input" name="cTrigger" [(ngModel)]="form.trigger">
                  @for (trigger of capabilities()?.triggers ?? []; track trigger.key) {
                    <option [value]="trigger.key" [disabled]="!trigger.available">
                      {{ trigger.label }}{{ trigger.available ? '' : ' · T-059' }}
                    </option>
                  }
                </select>
              </label>
              <label class="field">
                Prioridad
                <input class="input" type="number" min="1" name="cPriority" [(ngModel)]="form.priority" />
                <span class="muted tiny">1 = mayor prioridad. Si varias campañas coinciden al mismo tiempo, se intenta primero la de mayor prioridad.</span>
              </label>
              <label class="check-card">
                <input type="checkbox" name="cStack" [(ngModel)]="form.stackable" />
                <span>
                  <strong>Puede convivir con otra campaña en la misma evaluación</strong>
                  <small class="muted">Solo permite intentar más de una campaña elegible en ese mismo evento. No ignora campañas recibidas anteriormente ni futuras reglas de supresión.</small>
                </span>
              </label>
            </div>
          </section>

          <div class="rules editor-section stack">
            <div class="row spread">
              <div>
                <strong>3. A quién alcanza</strong>
                <div class="muted tiny">Condiciones de elegibilidad. Por ahora se cumplen TODAS (AND); las supresiones/exclusiones son una capa distinta y todavía están en análisis.</div>
              </div>
              <button class="btn btn-sm" type="button" (click)="addRule()">+ Condición</button>
            </div>
            @if (form.rules.length === 0) {
              <p class="muted small">Sin condiciones adicionales: alcanza con el disparador y la vigencia.</p>
            }
            @for (rule of form.rules; track $index; let i = $index) {
              @if (ruleCapability(rule.field); as capability) {
                <div class="rule-row">
                  <div class="rule-subject-stack">
                    <select class="input" [name]="'rField' + i" [(ngModel)]="rule.field" (ngModelChange)="resetRule(rule)">
                      @for (availableRule of ruleCapabilities(); track availableRule.key) {
                        <option [value]="availableRule.key">{{ availableRule.label }}</option>
                      }
                    </select>
                    @if (capability.subjectOptions.length > 0) {
                      <select class="input" [name]="'rSubject' + i" [(ngModel)]="rule.subject">
                        @for (option of capability.subjectOptions; track option.value) {
                          <option [value]="option.value">{{ option.label }}</option>
                        }
                      </select>
                    }
                    @for (filter of capability.filters; track filter.key) {
                      <label class="rule-filter">
                        <span>{{ filter.label }}</span>
                        @if (filter.valueType === 'enum') {
                          <select
                            class="input"
                            [name]="'rFilter' + i + filter.key"
                            [ngModel]="ruleFilterValue(rule, filter.key)"
                            (ngModelChange)="setRuleFilter(rule, filter.key, $event)"
                          >
                            @if (!filter.required) {
                              <option value="">Cualquiera</option>
                            }
                            @for (option of filter.options; track option.value) {
                              <option [value]="option.value">{{ option.label }}</option>
                            }
                          </select>
                        } @else {
                          <input
                            class="input"
                            [name]="'rFilter' + i + filter.key"
                            [ngModel]="ruleFilterValue(rule, filter.key)"
                            (ngModelChange)="setRuleFilter(rule, filter.key, $event)"
                            placeholder="Cualquiera"
                          />
                        }
                      </label>
                    }
                  </div>

                  <select class="input op" [name]="'rOp' + i" [(ngModel)]="rule.operator">
                    @for (operator of capability.operators; track operator) {
                      <option [value]="operator">{{ operatorLabel(operator, capability.valueType) }}</option>
                    }
                  </select>

                  <div class="rule-value-stack">
                    @switch (capability.valueType) {
                      @case ('boolean') {
                        <select class="input value" [name]="'rValue' + i" [(ngModel)]="rule.value">
                          <option [ngValue]="false">No</option>
                          <option [ngValue]="true">Sí</option>
                        </select>
                      }
                      @case ('enum') {
                        <select class="input value" [name]="'rValue' + i" [(ngModel)]="rule.value">
                          @for (option of capability.options; track option.value) {
                            <option [value]="option.value">{{ option.label }}</option>
                          }
                        </select>
                      }
                      @case ('integer') {
                        <input class="input value" type="number" min="0" step="1" [name]="'rValue' + i" [(ngModel)]="rule.value" />
                      }
                      @case ('number') {
                        <input class="input value" type="number" min="0" step="0.1" [name]="'rValue' + i" [(ngModel)]="rule.value" />
                      }
                      @case ('datetime') {
                        <input class="input value" type="datetime-local" [name]="'rValue' + i" [(ngModel)]="rule.value" />
                      }
                      @default {
                        <input class="input value" [name]="'rValue' + i" [(ngModel)]="rule.value" />
                      }
                    }
                    @if (capability.requiresWindow) {
                      <label class="window-field">
                        en los últimos
                        <input
                          class="input window-input"
                          type="number"
                          [min]="capability.windowMinDays ?? 1"
                          [max]="capability.windowMaxDays ?? 3650"
                          step="1"
                          [name]="'rWindow' + i"
                          [(ngModel)]="rule.windowDays"
                        />
                        días
                      </label>
                    }
                  </div>
                  <button class="btn btn-sm btn-danger" type="button" (click)="removeRule(i)">Quitar</button>
                </div>
                <div class="muted tiny rule-description">{{ capability.description }}</div>
              }
            }
          </div>

          <section class="editor-section stack">
            <div class="section-head">
              <div>
                <strong>4. Entrega</strong>
                <div class="muted tiny">Cómo se comunica el resultado cuando la campaña logra aplicarse.</div>
              </div>
            </div>
            <div class="grid">
              <label class="field">
                Notificación / entrega
                <select class="input" name="cNotification" [(ngModel)]="form.notification">
                  @for (delivery of capabilities()?.deliveries ?? []; track delivery.key) {
                    <option [value]="delivery.key">{{ delivery.label }}</option>
                  }
                </select>
                @if (form.notification === 'EMAIL' || form.notification === 'IN_APP_EMAIL') {
                  <span class="muted tiny">Se encola como pendiente; el envío real corresponde a T-051.</span>
                }
              </label>
              <label class="field">
                Mensaje
                <input class="input" name="cMessage" [(ngModel)]="form.message" maxlength="500"
                  placeholder="Se genera uno automático si queda vacío" />
              </label>
            </div>
          </section>

          <section class="editor-section stack">
            <div class="section-head">
              <div>
                <strong>5. Vigencia y límites</strong>
                <div class="muted tiny">Cuándo puede aplicarse y cuántas personas pueden recibirla en total.</div>
              </div>
            </div>
            <div class="grid">
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
          </section>

          @if (audiencePreview(); as preview) {
            <div class="preview-card">
              <div class="row spread">
                <strong>Previsualización de audiencia</strong>
                <span class="chip">{{ preview.eligibleCount }} de {{ preview.candidateCount }} coinciden</span>
              </div>
              @for (warning of preview.warnings; track warning) {
                <div class="warning tiny">{{ warning }}</div>
              }
              @if (preview.sample.length) {
                <div class="preview-sample">
                  @for (account of preview.sample; track account.accountId) {
                    <div class="preview-account" [class.preview-excluded]="!account.eligible">
                      <span><strong>{{ account.displayName || account.email }}</strong> · {{ account.email }}</span>
                      <span [class]="account.eligible ? 'chip chip-ok' : 'chip'">
                        {{ account.eligible ? 'Coincide' : 'No coincide' }}
                      </span>
                    </div>
                  }
                </div>
              }
            </div>
          }

          <div class="row">
            <button class="btn btn-sm" type="button" (click)="previewAudience()" [disabled]="previewLoading() || !canSave()">
              @if (previewLoading()) { <span class="spinner"></span> }
              Previsualizar audiencia
            </button>
            <button class="btn btn-primary btn-sm" type="submit" [disabled]="saving() || !canSave()">
              @if (saving()) { <span class="spinner"></span> } Guardar
            </button>
            <button class="btn btn-sm" type="button" (click)="cancelForm()">Cancelar</button>
          </div>
        </form>
        }
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
                  @if (campaign.stackable) { <span class="chip chip-ok">Convive</span> }
                </div>
                <div class="small">
                  {{ triggerLabel(campaign.trigger) }} · {{ actionLabel(campaign.action) }} → <strong>{{ campaign.benefitName }}</strong>
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
                    . Revisá prioridad y convivencia.
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
                } @else {
                  <button class="btn btn-sm btn-danger" type="button" (click)="deleteCampaign(campaign)">Eliminar</button>
                }
              </div>
            </article>
          }
        </div>
      }
    </app-collapse-card>
  `,
  styles: `
    :host { display: contents; }
    .collapse-actions { display: flex; justify-content: flex-end; margin-bottom: 0.8rem; }
    .creator, .editor, .rules { padding: 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; background: var(--bg); }
    .creator { margin-bottom: 0.8rem; }
    .creator-head { align-items: flex-start; }
    .creation-options, .template-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0.65rem;
    }
    .choice-card, .template-card {
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
      text-align: left;
      padding: 0.8rem;
      border: 1px solid var(--border);
      border-radius: 0.6rem;
      background: transparent;
      color: inherit;
      cursor: pointer;
      font: inherit;
    }
    .choice-card:hover, .template-card:hover { background: var(--bg); }
    .choice-card span, .template-card span { color: var(--muted); font-size: 0.82rem; line-height: 1.35; }
    .ai-description { min-height: 6.5rem; resize: vertical; }
    .draft-banner { margin-bottom: 0.8rem; }
    .draft-blocked { border-color: var(--warn); }
    .requirement-list { margin-top: 0.45rem; padding-top: 0.45rem; border-top: 1px solid var(--border); }
    .spread { justify-content: space-between; }
    .check-row { display: flex; gap: 0.5rem; align-items: flex-start; }
    .editor-section {
      padding: 0.85rem;
      border: 1px solid var(--border);
      border-radius: 0.7rem;
      background: var(--surface);
    }
    .section-head { display: flex; justify-content: space-between; gap: 0.75rem; }
    .check-card {
      display: flex;
      gap: 0.55rem;
      align-items: flex-start;
      padding: 0.65rem;
      border: 1px solid var(--border);
      border-radius: 0.55rem;
      cursor: pointer;
    }
    .check-card span { display: flex; flex-direction: column; gap: 0.18rem; }
    .check-card small { line-height: 1.35; }
    .rule-row { display: grid; grid-template-columns: minmax(10rem, 1.4fr) minmax(7rem, 0.7fr) minmax(8rem, 1fr) auto; gap: 0.5rem; align-items: center; }
    .rule-description { margin-top: -0.25rem; }
    .rule-subject-stack, .rule-value-stack { display: flex; flex-direction: column; gap: 0.3rem; }
    .rule-filter { display: flex; flex-direction: column; gap: 0.2rem; color: var(--muted); font-size: 0.72rem; }
    .window-field { display: flex; align-items: center; gap: 0.35rem; color: var(--muted); font-size: 0.76rem; white-space: nowrap; }
    .window-input { width: 5rem; padding-block: 0.25rem; }
    .operator { text-align: center; font-size: 0.86rem; color: var(--muted); }
    .preview-card { padding: 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; background: var(--surface); display: flex; flex-direction: column; gap: 0.55rem; }
    .preview-sample { display: flex; flex-direction: column; gap: 0.3rem; }
    .preview-account { display: flex; justify-content: space-between; gap: 0.6rem; align-items: center; font-size: 0.82rem; }
    .preview-excluded { opacity: 0.62; }
    .campaign-list { display: flex; flex-direction: column; gap: 0.55rem; }
    .campaign { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; padding: 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; }
    .campaign-main { display: flex; flex-direction: column; gap: 0.3rem; }
    .actions { flex: none; flex-wrap: wrap; justify-content: flex-end; }
    .warning { color: var(--warn); }
    .dim .campaign-main { opacity: 0.65; }
    .tiny { font-size: 0.76rem; }
    @media (max-width: 760px) {
      .creation-options, .template-grid { grid-template-columns: 1fr; }
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
  readonly benefits = signal<PlatformBenefit[]>([]);
  readonly capabilities = signal<PlatformCampaignCapabilities | null>(null);
  readonly capabilitiesError = signal('');
  readonly audiencePreview = signal<CampaignAudiencePreview | null>(null);
  readonly previewLoading = signal(false);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly editingId = signal<number | null>(null);
  readonly newMode = signal<NewCampaignMode>(null);
  readonly aiLoading = signal(false);
  readonly draftSummary = signal('');
  readonly draftWarnings = signal<string[]>([]);
  readonly draftBlockingIssues = signal<string[]>([]);
  readonly draftRequirements = signal<CampaignAssistRequirement[]>([]);
  readonly aiDraftExecutable = signal(true);
  readonly templates = CAMPAIGN_TEMPLATES;
  aiDescription = '';

  activeBenefits(): PlatformBenefit[] {
    return this.benefits().filter((benefit) => benefit.active);
  }

  form: CampaignForm = emptyForm(null);

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const [campaigns, benefits] = await Promise.all([
        firstValueFrom(this.api.platformCampaigns()),
        firstValueFrom(this.api.platformBenefits())
      ]);
      this.campaigns.set(campaigns);
      this.benefits.set(benefits);
    } catch (err) {
      this.toast.error(errorMessage(err));
    }

    try {
      this.capabilities.set(await firstValueFrom(this.api.platformCampaignCapabilities()));
      this.capabilitiesError.set('');
    } catch (err) {
      this.capabilities.set(null);
      const detail = errorMessage(err, 'error desconocido');
      this.capabilitiesError.set(
        'No se pudieron cargar las capacidades del motor. Verificá que estés usando esta misma rama, ' +
        'reiniciá el backend y recargá la pantalla. Detalle: ' + detail
      );
    } finally {
      this.loading.set(false);
    }
  }

  startNew(): void {
    this.editingId.set(null);
    this.draftSummary.set('');
    this.draftWarnings.set([]);
    this.draftBlockingIssues.set([]);
    this.draftRequirements.set([]);
    this.aiDraftExecutable.set(true);
    this.audiencePreview.set(null);
    this.aiDescription = '';
    this.newMode.set('choose');
  }

  startManual(): void {
    this.form = emptyForm(this.activeBenefits()[0]?.id ?? null);
    this.draftSummary.set('');
    this.draftWarnings.set([]);
    this.draftBlockingIssues.set([]);
    this.draftRequirements.set([]);
    this.aiDraftExecutable.set(true);
    this.audiencePreview.set(null);
    this.newMode.set(null);
    this.editingId.set(0);
  }

  applyTemplate(template: CampaignTemplate): void {
    this.form = {
      name: template.name,
      benefitId: null,
      action: 'GRANT_BENEFIT',
      actionConfig: {},
      trigger: template.trigger,
      rules: template.rules.map((rule) => ({ ...rule })),
      priority: template.priority,
      stackable: template.stackable,
      maxRecipients: template.maxRecipients,
      startsAt: template.startsAt ?? '',
      endsAt: template.endsAt ?? '',
      notification: template.notification,
      message: template.message
    };
    this.draftSummary.set(`Plantilla "${template.title}" aplicada. Revisá el beneficio y los valores antes de guardar.`);
    this.draftWarnings.set([]);
    this.draftBlockingIssues.set([]);
    this.draftRequirements.set([]);
    this.aiDraftExecutable.set(true);
    this.newMode.set(null);
    this.editingId.set(0);
  }

  cancelNew(): void {
    this.newMode.set(null);
    this.aiDescription = '';
  }

  cancelForm(): void {
    this.editingId.set(null);
    this.draftSummary.set('');
    this.draftWarnings.set([]);
    this.draftBlockingIssues.set([]);
    this.draftRequirements.set([]);
    this.aiDraftExecutable.set(true);
    this.audiencePreview.set(null);
  }

  async generateWithAi(): Promise<void> {
    const description = this.aiDescription.trim();
    if (description.length < 8) return;

    this.aiLoading.set(true);
    try {
      const result = await firstValueFrom(this.api.assistPlatformCampaign(description));
      this.form = {
        name: result.draft.name,
        benefitId: result.draft.benefitId,
        action: result.draft.action ?? 'GRANT_BENEFIT',
        actionConfig: result.draft.actionConfig ?? {},
        trigger: result.draft.trigger,
        rules: result.draft.rules.map((rule) => this.ruleForForm(rule)),
        priority: result.draft.priority,
        stackable: result.draft.stackable,
        maxRecipients: result.draft.maxRecipients,
        startsAt: localDate(result.draft.startsAt),
        endsAt: localDate(result.draft.endsAt),
        notification: result.draft.notification,
        message: result.draft.message ?? ''
      };
      this.draftSummary.set(result.summary || 'Borrador generado por IA. Revisalo antes de guardar.');
      this.draftWarnings.set(result.warnings ?? []);
      this.draftBlockingIssues.set(result.blockingIssues ?? []);
      this.draftRequirements.set(result.requirements ?? []);
      this.aiDraftExecutable.set(result.executable === true);
      this.newMode.set(null);
      this.editingId.set(0);
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo generar el borrador con IA.'));
    } finally {
      this.aiLoading.set(false);
    }
  }

  startEdit(campaign: PlatformCampaign): void {
    this.form = {
      name: campaign.name,
      benefitId: campaign.benefitId,
      action: campaign.action ?? 'GRANT_BENEFIT',
      actionConfig: campaign.actionConfig ?? {},
      trigger: campaign.trigger,
      rules: campaign.rules.map((rule) => this.ruleForForm(rule)),
      priority: campaign.priority,
      stackable: campaign.stackable,
      maxRecipients: campaign.maxRecipients,
      startsAt: localDate(campaign.startsAt),
      endsAt: localDate(campaign.endsAt),
      notification: campaign.notification,
      message: campaign.message ?? ''
    };
    this.newMode.set(null);
    this.draftSummary.set('');
    this.draftWarnings.set([]);
    this.draftBlockingIssues.set([]);
    this.draftRequirements.set([]);
    this.aiDraftExecutable.set(true);
    this.audiencePreview.set(null);
    this.editingId.set(campaign.id);
  }

  addRule(): void {
    this.form.rules.push({ field: 'ACCOUNT_TYPE', operator: 'EQ', value: 'PERSONAL' });
    this.audiencePreview.set(null);
  }

  removeRule(index: number): void {
    this.form.rules.splice(index, 1);
    this.audiencePreview.set(null);
  }

  ruleCapabilities(): CampaignRuleCapability[] {
    return (this.capabilities()?.rules ?? []).filter((rule) => rule.available);
  }

  ruleCapability(field: string): CampaignRuleCapability | null {
    return this.ruleCapabilities().find((rule) => rule.key === field) ?? null;
  }

  operatorLabel(operator: string, valueType: CampaignRuleCapability['valueType']): string {
    if (valueType === 'datetime') {
      return operator === 'GTE' ? 'desde' : operator === 'LTE' ? 'hasta' : 'exactamente';
    }
    return operator === 'GTE' ? 'al menos' : operator === 'LTE' ? 'como máximo' : 'es';
  }

  private ruleForForm(rule: CampaignRule): CampaignRule {
    const capability = this.ruleCapability(rule.field);
    return {
      ...rule,
      filters: { ...(rule.filters ?? {}) },
      value:
        capability?.valueType === 'datetime' && typeof rule.value === 'string'
          ? localDate(rule.value)
          : rule.value
    };
  }

  ruleFilterValue(rule: CampaignRule, key: string): string {
    return rule.filters?.[key] ?? '';
  }

  setRuleFilter(rule: CampaignRule, key: string, value: string): void {
    rule.filters = { ...(rule.filters ?? {}), [key]: value };
    this.audiencePreview.set(null);
  }

  private ruleForApi(rule: CampaignRule): CampaignRule {
    const capability = this.ruleCapability(rule.field);
    let value = rule.value;
    if (capability?.valueType === 'integer' || capability?.valueType === 'number') {
      value = Number(value);
    } else if (capability?.valueType === 'datetime' && value) {
      value = new Date(String(value)).toISOString();
    }
    const filters = Object.fromEntries(
      Object.entries(rule.filters ?? {}).filter(([, filterValue]) => String(filterValue).trim() !== '')
    );
    return {
      ...rule,
      filters,
      value,
      windowDays: capability?.requiresWindow ? Number(rule.windowDays) : null
    };
  }

  resetRule(rule: CampaignRule): void {
    const capability = this.ruleCapability(rule.field);
    rule.operator = capability?.operators[0] ?? 'EQ';
    if (!capability) {
      rule.subject = null;
      rule.filters = {};
      rule.value = '';
      return;
    }
    rule.subject = capability.subjectOptions[0]?.value ?? null;
    rule.filters = Object.fromEntries(
      capability.filters
        .filter((filter) => filter.required)
        .map((filter) => [filter.key, filter.options[0]?.value ?? ''])
    );
    if (capability.valueType === 'boolean') {
      rule.value = false;
    } else if (capability.valueType === 'integer' || capability.valueType === 'number') {
      rule.value = 0;
    } else if (capability.valueType === 'enum') {
      rule.value = capability.options[0]?.value ?? '';
    } else {
      rule.value = '';
    }
    rule.windowDays = capability.requiresWindow ? 30 : null;
    this.audiencePreview.set(null);
  }

  canSave(): boolean {
    return (
      this.aiDraftExecutable() &&
      !!this.capabilities() &&
      !!this.form.name.trim() &&
      !!this.form.benefitId &&
      this.form.action === 'GRANT_BENEFIT' &&
      this.form.priority > 0 &&
      this.form.rules.every((rule) => {
        const capability = this.ruleCapability(rule.field);
        const subjectOk = !capability?.subjectOptions.length || !!rule.subject;
        const filtersOk = (capability?.filters ?? []).every(
          (filter) => !filter.required || !!rule.filters?.[filter.key]
        );
        const windowOk = !capability?.requiresWindow || Number(rule.windowDays) > 0;
        return subjectOk && filtersOk && windowOk;
      })
    );
  }

  private buildDraft(): PlatformCampaignDraft | null {
    if (!this.canSave() || !this.form.benefitId) return null;
    return {
      name: this.form.name.trim(),
      benefitId: this.form.benefitId,
      action: this.form.action,
      actionConfig: this.form.actionConfig ?? {},
      trigger: this.form.trigger,
      rules: this.form.rules.map((rule) => this.ruleForApi(rule)),
      priority: Math.max(1, Math.round(Number(this.form.priority) || 100)),
      stackable: this.form.stackable,
      maxRecipients: numberOrNull(this.form.maxRecipients),
      startsAt: isoDate(this.form.startsAt),
      endsAt: isoDate(this.form.endsAt),
      notification: this.form.notification,
      message: this.form.message.trim() || null
    };
  }

  async previewAudience(): Promise<void> {
    const draft = this.buildDraft();
    if (!draft) return;
    this.previewLoading.set(true);
    try {
      this.audiencePreview.set(await firstValueFrom(this.api.previewPlatformCampaign(draft)));
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo previsualizar la audiencia.'));
    } finally {
      this.previewLoading.set(false);
    }
  }

  async save(): Promise<void> {
    const id = this.editingId();
    const draft = this.buildDraft();
    if (id === null || !draft) return;
    this.saving.set(true);
    try {
      await firstValueFrom(
        id ? this.api.updatePlatformCampaign(id, draft) : this.api.createPlatformCampaign(draft)
      );
      this.toast.success(id ? 'Campaña actualizada.' : 'Campaña creada en borrador.');
      this.cancelForm();
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

  async deleteCampaign(campaign: PlatformCampaign): Promise<void> {
    const history = campaign.recipients > 0
      ? ' Tiene beneficiarios: se ocultará la campaña pero se conservará su historial.'
      : ' No tiene beneficiarios: se eliminará definitivamente.';
    if (!confirm('¿Eliminar la campaña "' + campaign.name + '"?' + history)) return;
    try {
      await firstValueFrom(this.api.deletePlatformCampaign(campaign.id));
      this.toast.success('Campaña eliminada.');
      await this.load();
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }
  triggerLabel(trigger: CampaignTrigger): string {
    return trigger === 'FIRST_LOGIN' ? 'Primer login' : trigger === 'LOGIN' ? 'Cada login' : 'Programada';
  }

  actionLabel(action: CampaignAction): string {
    return this.capabilities()?.actions.find((item) => item.key === action)?.label ?? action;
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
