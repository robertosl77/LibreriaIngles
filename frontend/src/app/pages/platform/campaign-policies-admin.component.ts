import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import {
  CampaignPolicyAssistRequirement,
  CampaignPolicyBlock,
  CampaignPolicyKind,
  CampaignPolicyRule,
  CampaignPolicyRuleCapability,
  PlatformCampaign,
  PlatformCampaignPolicy,
  PlatformCampaignPolicyCapabilities,
  PlatformCampaignPolicyDraft
} from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';
import {
  CAMPAIGN_POLICY_TEMPLATES,
  CampaignPolicyTemplate,
  campaignPolicyTemplateIssues
} from './campaign-policy-templates';

type NewPolicyMode = 'choose' | 'templates' | 'ai' | null;

interface PolicyForm {
  name: string;
  description: string;
  kind: CampaignPolicyKind;
  enabled: boolean;
  appliesToMode: 'ALL' | 'CAMPAIGNS';
  campaignIds: number[];
  rules: CampaignPolicyRule[];
}

function defaultRule(): CampaignPolicyRule {
  return {
    field: 'CAMPAIGN_GRANTS_COUNT',
    operator: 'GTE',
    value: 1,
    windowDays: 30
  };
}

function emptyForm(): PolicyForm {
  return {
    name: '',
    description: '',
    kind: 'SUPPRESSION',
    enabled: true,
    appliesToMode: 'ALL',
    campaignIds: [],
    rules: [defaultRule()]
  };
}

@Component({
  selector: 'app-campaign-policies-admin',
  imports: [FormsModule, CollapseCardComponent],
  template: `
    <app-collapse-card
      title="Políticas globales"
      description="Reglas reutilizables que pueden bloquear una campaña candidata antes de prioridad y convivencia."
    >
      @if (editingId() === null && !newMode()) {
        <div class="collapse-actions">
          <button class="btn btn-sm" type="button" (click)="startNew()">Nueva política</button>
        </div>
      }

      <div class="policy-explanation">
        <strong>Orden del motor</strong>
        <span>Match de campaña → políticas globales → prioridad/convivencia → acción.</span>
        <span>Si una política bloquea, esa campaña no ocupa lugar en convivencia para esa persona.</span>
      </div>

      @if (newMode()) {
        <section class="policy-creator stack">
          <div class="row spread creator-head">
            <div>
              <strong>Nueva política global</strong>
              <div class="muted small">
                Los tres caminos terminan en el mismo formulario revisable.
              </div>
            </div>
            <button class="btn btn-sm" type="button" (click)="cancelNew()">Cancelar</button>
          </div>

          @if (newMode() === 'choose') {
            <div class="creation-options">
              <button class="choice-card" type="button" (click)="newMode.set('templates')">
                <strong>Usar plantilla</strong>
                <span>Partí de reglas frecuentes de supresión y ajustá sus valores.</span>
              </button>
              <button class="choice-card" type="button" (click)="newMode.set('ai')">
                <strong>Describir con IA</strong>
                <span>Contá la política en lenguaje natural y recibí un borrador revisable.</span>
              </button>
              <button class="choice-card" type="button" (click)="startManual()">
                <strong>Configurar manualmente</strong>
                <span>Usá directamente el constructor de políticas globales.</span>
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
                @if (templateIssues(template); as issues) {
                  <button
                    class="template-card"
                    type="button"
                    (click)="applyTemplate(template)"
                    [disabled]="issues.length > 0"
                  >
                    <strong>{{ template.title }}</strong>
                    <span>{{ template.description }}</span>
                    @if (issues.length > 0) {
                      <span class="template-invalid">Requiere revisión: {{ issues.join(' · ') }}</span>
                    } @else {
                      <span class="template-ok">Compatible con el catálogo actual</span>
                    }
                  </button>
                }
              }
            </div>
          }

          @if (newMode() === 'ai') {
            <div class="row spread">
              <strong>Describí la política</strong>
              <button class="btn btn-sm" type="button" (click)="newMode.set('choose')">Volver</button>
            </div>
            <label class="field">
              Qué querés impedir
              <textarea
                class="input ai-description"
                name="policyAiDescription"
                [(ngModel)]="aiDescription"
                maxlength="2000"
                rows="4"
                placeholder="Ej. No activar una campaña si la persona recibió otra campaña durante los últimos 30 días."
              ></textarea>
            </label>
            <p class="muted tiny">
              La IA usa una conexión de la plataforma y genera únicamente un borrador con las
              capacidades actuales. Nunca guarda ni habilita una política.
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
        <section class="policy-form stack">
          @if (draftSummary()) {
            <div class="banner small draft-banner" [class.draft-blocked]="!aiDraftExecutable()">
              <strong>{{ draftSummary() }}</strong>
              @if (!aiDraftExecutable()) {
                <div class="warning">
                  <strong>Borrador incompleto: no se puede guardar.</strong>
                </div>
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

          <div class="row spread">
            <div>
              <strong>{{ editingId() === 0 ? 'Nueva política' : 'Editar política' }}</strong>
              <div class="muted small">
                En esta primera versión solo Supresión está habilitada. Exclusión queda reservada para el mismo motor.
              </div>
            </div>
            <button class="btn btn-sm" type="button" (click)="cancel()">Cancelar</button>
          </div>

          <div class="grid two">
            <label class="field">
              Nombre
              <input class="input" name="pName" maxlength="120" [(ngModel)]="form.name"
                placeholder="Ej. Enfriamiento general de 30 días" />
            </label>

            <label class="field">
              Tipo
              <select class="input" name="pKind" [(ngModel)]="form.kind">
                @for (kind of capabilities()?.kinds ?? []; track kind.key) {
                  <option [value]="kind.key" [disabled]="!kind.available">
                    {{ kind.label }}{{ kind.available ? '' : ' · todavía en análisis' }}
                  </option>
                }
              </select>
            </label>
          </div>

          <label class="field">
            Descripción
            <textarea class="input" name="pDescription" rows="2" maxlength="500"
              [(ngModel)]="form.description"
              placeholder="Explicá la regla de negocio para que después sea auditable."></textarea>
          </label>

          <div class="scope-card stack">
            <div>
              <strong>A qué campañas aplica</strong>
              <div class="muted small">
                Esto define el alcance de la política. No es prioridad ni convivencia.
              </div>
            </div>
            <label class="field">
              Alcance
              <select class="input" name="pAppliesTo" [(ngModel)]="form.appliesToMode"
                (ngModelChange)="appliesToChanged()">
                <option value="ALL">Todas las campañas</option>
                <option value="CAMPAIGNS">Solo campañas seleccionadas</option>
              </select>
            </label>

            @if (form.appliesToMode === 'CAMPAIGNS') {
              <div class="campaign-picker">
                @for (campaign of campaigns(); track campaign.id) {
                  <label class="campaign-option">
                    <input
                      type="checkbox"
                      [checked]="form.campaignIds.includes(campaign.id)"
                      (change)="toggleCampaign(campaign.id, $any($event.target).checked)"
                    />
                    <span>
                      <strong>{{ campaign.name }}</strong>
                      <small>P{{ campaign.priority }} · {{ campaign.status }}</small>
                    </span>
                  </label>
                }
              </div>
            }
          </div>

          <div class="rules-card stack">
            <div class="row spread">
              <div>
                <strong>Cuándo bloquea</strong>
                <div class="muted small">
                  Dentro de una política se cumplen todas las condiciones (AND). Entre políticas, cualquiera que bloquee alcanza (OR).
                </div>
              </div>
              <button class="btn btn-sm" type="button" (click)="addRule()">+ Condición</button>
            </div>

            @for (rule of form.rules; track $index; let i = $index) {
              <div class="rule-row">
                <label class="field">
                  Condición
                  <select class="input" [name]="'pRuleField' + i" [(ngModel)]="rule.field"
                    (ngModelChange)="resetRule(rule)">
                    @for (capability of ruleCapabilities(); track capability.key) {
                      <option [value]="capability.key">{{ capability.label }}</option>
                    }
                  </select>
                </label>

                <label class="field compact">
                  Operador
                  <select class="input" [name]="'pRuleOperator' + i" [(ngModel)]="rule.operator">
                    @for (operator of ruleCapability(rule.field)?.operators ?? []; track operator) {
                      <option [value]="operator">{{ operatorLabel(operator) }}</option>
                    }
                  </select>
                </label>

                <label class="field compact">
                  Cantidad
                  <input class="input" type="number" min="0" [name]="'pRuleValue' + i"
                    [(ngModel)]="rule.value" />
                </label>

                <label class="field compact">
                  Últimos días
                  <input class="input" type="number" min="1" max="3650" [name]="'pRuleWindow' + i"
                    [(ngModel)]="rule.windowDays" />
                </label>

                <button class="btn btn-sm btn-danger rule-remove" type="button"
                  [disabled]="form.rules.length === 1" (click)="removeRule(i)">
                  Quitar
                </button>
              </div>
              @if (ruleCapability(rule.field); as capability) {
                <div class="muted tiny rule-help">{{ capability.description }}</div>
              }
            }
          </div>

          <label class="check-row">
            <input type="checkbox" name="pEnabled" [(ngModel)]="form.enabled" />
            <span>
              <strong>Política habilitada</strong>
              <small>Si está deshabilitada se conserva, pero no participa de ninguna evaluación.</small>
            </span>
          </label>

          <div class="row form-actions">
            <button class="btn btn-primary" type="button" [disabled]="!canSave() || saving()"
              (click)="save()">
              {{ saving() ? 'Guardando…' : 'Guardar política' }}
            </button>
            <button class="btn" type="button" [disabled]="saving()" (click)="cancel()">Cancelar</button>
          </div>
        </section>
      }

      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else if (policies().length === 0) {
        <p class="muted">Todavía no hay políticas globales.</p>
      } @else {
        <div class="policy-list">
          @for (policy of policies(); track policy.id) {
            <article class="policy-row" [class.policy-disabled]="!policy.enabled">
              <div class="policy-main">
                <div class="row">
                  <strong>{{ policy.name }}</strong>
                  <span class="chip">{{ kindLabel(policy.kind) }}</span>
                  <span [class]="policy.enabled ? 'chip chip-ok' : 'chip'">
                    {{ policy.enabled ? 'Habilitada' : 'Deshabilitada' }}
                  </span>
                </div>
                @if (policy.description) {
                  <div class="small">{{ policy.description }}</div>
                }
                <div class="muted small">
                  {{ appliesLabel(policy) }} · {{ policy.rules.length }} condición(es)
                  · {{ policy.blockCount }} bloqueo(s)
                  @if (policy.lastBlockedAt) {
                    · último {{ formatDate(policy.lastBlockedAt) }}
                  }
                </div>
                <div class="rule-summary">
                  @for (rule of policy.rules; track $index) {
                    <span class="chip">{{ ruleSummary(rule) }}</span>
                  }
                </div>
              </div>

              <div class="actions row">
                <button class="btn btn-sm" type="button" (click)="startEdit(policy)">Editar</button>
                <button class="btn btn-sm" type="button"
                  (click)="changeEnabled(policy, !policy.enabled)">
                  {{ policy.enabled ? 'Deshabilitar' : 'Habilitar' }}
                </button>
                <button class="btn btn-sm btn-danger" type="button" (click)="deletePolicy(policy)">
                  Eliminar
                </button>
              </div>
            </article>
          }
        </div>
      }
    </app-collapse-card>

    <app-collapse-card
      title="Bloqueos por políticas"
      description="Auditoría reciente: qué campaña fue bloqueada, para quién y por qué."
    >
      @if (blocks().length === 0) {
        <p class="muted">Todavía no hay campañas bloqueadas por políticas.</p>
      } @else {
        <div class="block-list">
          @for (block of blocks(); track block.id) {
            <article class="block-row">
              <div>
                <strong>{{ block.account }}</strong>
                <div class="small">
                  {{ block.campaign }} → <strong>{{ block.policy }}</strong>
                </div>
                <div class="muted small">{{ block.reason }}</div>
              </div>
              <time class="muted tiny">{{ formatDate(block.createdAt) }}</time>
            </article>
          }
        </div>
      }
    </app-collapse-card>
  `,
  styles: `
    :host { display: contents; }
    .stack { display: grid; gap: 14px; }
    .grid.two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .field { display: grid; gap: 6px; font-size: .9rem; }
    .field.compact { min-width: 120px; }
    .input { width: 100%; }
    .policy-explanation {
      display: grid;
      gap: 4px;
      margin: 0 0 14px;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
    }
    .policy-explanation span { font-size: .82rem; }
    .policy-form {
      margin-bottom: 18px;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 12px;
    }
    .policy-creator {
      margin-bottom: 14px;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 12px;
    }
    .creator-head { align-items: flex-start; }
    .creation-options, .template-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .choice-card, .template-card {
      display: grid;
      gap: 6px;
      text-align: left;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: var(--surface);
      cursor: pointer;
    }
    .choice-card span, .template-card span { font-size: .82rem; color: var(--muted); }
    .template-card:disabled { cursor: not-allowed; opacity: .62; }
    .template-invalid { color: var(--warn) !important; }
    .template-ok { font-size: .74rem !important; }
    .ai-description { resize: vertical; }
    .draft-banner {
      display: grid;
      gap: 4px;
      padding: 10px 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
    }
    .draft-blocked { border-color: var(--warn); }
    .requirement-list { display: grid; gap: 2px; margin-top: 4px; }
    .warning { color: var(--warn); }
    .scope-card, .rules-card {
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
    }
    .campaign-picker {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      max-height: 260px;
      overflow: auto;
    }
    .campaign-option, .check-row {
      display: flex;
      gap: 9px;
      align-items: flex-start;
      padding: 8px;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
    .campaign-option span, .check-row span { display: grid; gap: 2px; }
    .campaign-option small, .check-row small { color: var(--muted); }
    .rule-row {
      display: grid;
      grid-template-columns: minmax(220px, 1.5fr) minmax(120px, .7fr) minmax(100px, .6fr) minmax(110px, .7fr) auto;
      gap: 8px;
      align-items: end;
    }
    .rule-remove { margin-bottom: 1px; }
    .rule-help { margin-top: -8px; }
    .policy-list, .block-list { display: grid; gap: 8px; }
    .policy-row, .block-row {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 10px;
    }
    .policy-disabled { opacity: .66; }
    .policy-main { display: grid; gap: 6px; min-width: 0; }
    .rule-summary { display: flex; flex-wrap: wrap; gap: 5px; }
    .block-row time { white-space: nowrap; }
    .form-actions { margin-top: 2px; }
    @media (max-width: 900px) {
      .grid.two, .campaign-picker, .creation-options, .template-grid { grid-template-columns: 1fr; }
      .rule-row { grid-template-columns: 1fr 1fr; }
      .rule-remove { justify-self: start; }
      .policy-row, .block-row { flex-direction: column; }
    }
    @media (max-width: 560px) {
      .rule-row { grid-template-columns: 1fr; }
    }
  `
})
export class CampaignPoliciesAdminComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly policies = signal<PlatformCampaignPolicy[]>([]);
  readonly campaigns = signal<PlatformCampaign[]>([]);
  readonly capabilities = signal<PlatformCampaignPolicyCapabilities | null>(null);
  readonly blocks = signal<CampaignPolicyBlock[]>([]);
  readonly editingId = signal<number | null>(null);
  readonly newMode = signal<NewPolicyMode>(null);
  readonly aiLoading = signal(false);
  readonly aiDraftExecutable = signal(true);
  readonly draftSummary = signal('');
  readonly draftWarnings = signal<string[]>([]);
  readonly draftBlockingIssues = signal<string[]>([]);
  readonly draftRequirements = signal<CampaignPolicyAssistRequirement[]>([]);
  readonly templates = CAMPAIGN_POLICY_TEMPLATES;
  aiDescription = '';

  form: PolicyForm = emptyForm();

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const [policies, campaigns, capabilities, blocks] = await Promise.all([
        firstValueFrom(this.api.platformCampaignPolicies()),
        firstValueFrom(this.api.platformCampaigns()),
        firstValueFrom(this.api.platformCampaignPolicyCapabilities()),
        firstValueFrom(this.api.platformCampaignPolicyBlocks())
      ]);
      this.policies.set(policies);
      this.campaigns.set(campaigns);
      this.capabilities.set(capabilities);
      this.blocks.set(blocks);
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudieron cargar las políticas globales.'));
    } finally {
      this.loading.set(false);
    }
  }

  private resetDraftFeedback(): void {
    this.draftSummary.set('');
    this.draftWarnings.set([]);
    this.draftBlockingIssues.set([]);
    this.draftRequirements.set([]);
    this.aiDraftExecutable.set(true);
  }

  startNew(): void {
    this.form = emptyForm();
    this.editingId.set(null);
    this.resetDraftFeedback();
    this.aiDescription = '';
    this.newMode.set('choose');
  }

  startManual(): void {
    this.form = emptyForm();
    this.resetDraftFeedback();
    this.newMode.set(null);
    this.editingId.set(0);
  }

  templateIssues(template: CampaignPolicyTemplate): string[] {
    const capabilities = this.capabilities();
    return capabilities
      ? campaignPolicyTemplateIssues(template, capabilities)
      : ['Catálogo no disponible'];
  }

  applyTemplate(template: CampaignPolicyTemplate): void {
    const issues = this.templateIssues(template);
    if (issues.length > 0) {
      this.toast.error('La plantilla no es compatible con el catálogo actual: ' + issues.join(' · '));
      return;
    }
    this.form = {
      name: template.draft.name,
      description: template.draft.description ?? '',
      kind: template.draft.kind,
      enabled: template.draft.enabled,
      appliesToMode: template.draft.appliesTo.mode,
      campaignIds: [...template.draft.appliesTo.campaignIds],
      rules: template.draft.rules.map((rule) => ({ ...rule }))
    };
    this.resetDraftFeedback();
    this.draftSummary.set(
      `Plantilla "${template.title}" aplicada. Revisá el alcance y los valores antes de guardar.`
    );
    this.newMode.set(null);
    this.editingId.set(0);
  }

  cancelNew(): void {
    this.newMode.set(null);
    this.aiDescription = '';
  }

  async generateWithAi(): Promise<void> {
    const description = this.aiDescription.trim();
    if (description.length < 8) return;

    this.aiLoading.set(true);
    try {
      const result = await firstValueFrom(this.api.assistPlatformCampaignPolicy(description));
      this.form = {
        name: result.draft.name,
        description: result.draft.description ?? '',
        kind: result.draft.kind,
        enabled: result.draft.enabled,
        appliesToMode: result.draft.appliesTo.mode,
        campaignIds: [...result.draft.appliesTo.campaignIds],
        rules: result.draft.rules.map((rule) => ({ ...rule }))
      };
      this.draftSummary.set(result.summary || 'Borrador generado por IA. Revisalo antes de guardar.');
      this.draftWarnings.set(result.warnings ?? []);
      this.draftBlockingIssues.set(result.blockingIssues ?? []);
      this.draftRequirements.set(result.requirements ?? []);
      this.aiDraftExecutable.set(result.executable === true);
      this.newMode.set(null);
      this.editingId.set(0);
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo generar el borrador de política con IA.'));
    } finally {
      this.aiLoading.set(false);
    }
  }

  startEdit(policy: PlatformCampaignPolicy): void {
    this.form = {
      name: policy.name,
      description: policy.description ?? '',
      kind: policy.kind,
      enabled: policy.enabled,
      appliesToMode: policy.appliesTo.mode,
      campaignIds: [...policy.appliesTo.campaignIds],
      rules: policy.rules.map((rule) => ({ ...rule }))
    };
    this.newMode.set(null);
    this.resetDraftFeedback();
    this.editingId.set(policy.id);
  }

  cancel(): void {
    this.editingId.set(null);
    this.newMode.set(null);
    this.aiDescription = '';
    this.resetDraftFeedback();
    this.form = emptyForm();
  }

  appliesToChanged(): void {
    if (this.form.appliesToMode === 'ALL') {
      this.form.campaignIds = [];
    }
  }

  toggleCampaign(id: number, checked: boolean): void {
    if (checked && !this.form.campaignIds.includes(id)) {
      this.form.campaignIds = [...this.form.campaignIds, id];
    } else if (!checked) {
      this.form.campaignIds = this.form.campaignIds.filter((campaignId) => campaignId !== id);
    }
  }

  ruleCapabilities(): CampaignPolicyRuleCapability[] {
    return (this.capabilities()?.rules ?? []).filter((rule) => rule.available);
  }

  ruleCapability(field: string): CampaignPolicyRuleCapability | null {
    return this.ruleCapabilities().find((rule) => rule.key === field) ?? null;
  }

  addRule(): void {
    this.form.rules.push(defaultRule());
  }

  removeRule(index: number): void {
    if (this.form.rules.length > 1) {
      this.form.rules.splice(index, 1);
    }
  }

  resetRule(rule: CampaignPolicyRule): void {
    const capability = this.ruleCapability(rule.field);
    if (!capability) return;
    rule.operator = capability.operators[0] ?? 'GTE';
    rule.value = 1;
    rule.windowDays = capability.windowMinDays === null ? 30 : Math.max(30, capability.windowMinDays);
  }

  operatorLabel(operator: string): string {
    return operator === 'GTE' ? 'al menos' : operator === 'LTE' ? 'como máximo' : 'exactamente';
  }

  canSave(): boolean {
    return (
      this.aiDraftExecutable() &&
      !!this.form.name.trim() &&
      this.form.kind === 'SUPPRESSION' &&
      this.form.rules.length > 0 &&
      (this.form.appliesToMode === 'ALL' || this.form.campaignIds.length > 0) &&
      this.form.rules.every((rule) =>
        !!this.ruleCapability(rule.field) &&
        Number(rule.value) >= 0 &&
        Number(rule.windowDays) >= 1
      )
    );
  }

  private draft(): PlatformCampaignPolicyDraft | null {
    if (!this.canSave()) return null;
    return {
      name: this.form.name.trim(),
      description: this.form.description.trim() || null,
      kind: this.form.kind,
      enabled: this.form.enabled,
      appliesTo: {
        mode: this.form.appliesToMode,
        campaignIds: this.form.appliesToMode === 'ALL'
          ? []
          : [...this.form.campaignIds].sort((a, b) => a - b)
      },
      rules: this.form.rules.map((rule) => ({
        field: rule.field,
        operator: rule.operator,
        value: Math.max(0, Math.round(Number(rule.value) || 0)),
        windowDays: Math.max(1, Math.round(Number(rule.windowDays) || 1))
      }))
    };
  }

  async save(): Promise<void> {
    const draft = this.draft();
    if (!draft) return;
    const id = this.editingId();
    this.saving.set(true);
    try {
      await firstValueFrom(
        id && id > 0
          ? this.api.updatePlatformCampaignPolicy(id, draft)
          : this.api.createPlatformCampaignPolicy(draft)
      );
      this.toast.success(id && id > 0 ? 'Política actualizada.' : 'Política creada.');
      this.cancel();
      await this.load();
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo guardar la política.'));
    } finally {
      this.saving.set(false);
    }
  }

  async changeEnabled(policy: PlatformCampaignPolicy, enabled: boolean): Promise<void> {
    try {
      await firstValueFrom(
        enabled
          ? this.api.enablePlatformCampaignPolicy(policy.id)
          : this.api.disablePlatformCampaignPolicy(policy.id)
      );
      await this.load();
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo cambiar el estado de la política.'));
    }
  }

  async deletePolicy(policy: PlatformCampaignPolicy): Promise<void> {
    if (!window.confirm(`Eliminar la política "${policy.name}"? El historial de bloqueos se conservará.`)) {
      return;
    }
    try {
      await firstValueFrom(this.api.deletePlatformCampaignPolicy(policy.id));
      this.toast.success('Política eliminada.');
      await this.load();
    } catch (err) {
      this.toast.error(errorMessage(err, 'No se pudo eliminar la política.'));
    }
  }

  kindLabel(kind: CampaignPolicyKind): string {
    return kind === 'SUPPRESSION' ? 'Supresión' : 'Exclusión';
  }

  appliesLabel(policy: PlatformCampaignPolicy): string {
    if (policy.appliesTo.mode === 'ALL') {
      return 'Aplica a todas las campañas';
    }
    const names = policy.appliesTo.campaignIds
      .map((id) => this.campaigns().find((campaign) => campaign.id === id)?.name ?? `#${id}`)
      .join(', ');
    return `Aplica a: ${names || 'campañas seleccionadas'}`;
  }

  ruleSummary(rule: CampaignPolicyRule): string {
    const label = this.ruleCapability(rule.field)?.label ?? rule.field;
    return `${label} · ${this.operatorLabel(rule.operator)} ${rule.value} · ${rule.windowDays} días`;
  }

  formatDate(value: string): string {
    return new Date(value).toLocaleString();
  }
}
