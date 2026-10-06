import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import {
  JobTitleOption,
  OrganizationActingCapacity,
  OrganizationCompanyLookupResult,
  OrganizationOnboardingConfig,
  OrganizationOnboardingResult
} from '../../core/models';

@Component({
  selector: 'app-organization-onboarding',
  imports: [FormsModule, RouterLink],
  template: `
    <main class="onboarding">
      <header class="topbar">
        <a class="brand" routerLink="/">Librería Inglés</a>
        <a class="back" routerLink="/">Volver al inicio</a>
      </header>

      <section class="heading">
        <p class="eyebrow">Empresas · P01</p>
        <h1>Registrar una organización</h1>
        <p>
          En este primer paso identificamos la empresa y a la persona que inicia el trámite.
          La organización todavía no se crea dentro de la plataforma.
        </p>
      </section>

      @if (loading()) {
        <section class="panel"><p>Cargando configuración…</p></section>
      } @else {
        <section class="panel stack">
          <div>
            <p class="step">Paso 1</p>
            <h2>Identificar la empresa</h2>
            <p class="muted">
              Empezamos con Argentina. La arquitectura admite otros países e identificadores fiscales
              sin convertir CUIT en una regla universal.
            </p>
          </div>

          <div class="grid two">
            <label class="field">
              País
              <select class="input" [(ngModel)]="country" disabled>
                @for (item of config()?.countries ?? []; track item.code) {
                  <option [value]="item.code">{{ item.name }}</option>
                }
              </select>
            </label>

            <label class="field">
              Identificación fiscal
              <select class="input" [(ngModel)]="taxIdType" disabled>
                <option value="CUIT">CUIT</option>
              </select>
            </label>
          </div>

          <label class="field">
            CUIT
            <input
              class="input"
              name="taxId"
              [(ngModel)]="taxId"
              (ngModelChange)="resetLookup()"
              placeholder="30-12345678-1"
              autocomplete="off"
              [disabled]="companyLocked()"
            />
          </label>

          <div class="search-actions">
            <button
              class="btn primary"
              type="button"
              (click)="lookupCompany()"
              [disabled]="lookupBusy() || companyLocked() || !taxId.trim()"
            >
              {{
                companyLocked()
                  ? 'Empresa seleccionada'
                  : lookupBusy()
                    ? 'Consultando…'
                    : 'Buscar empresa'
              }}
            </button>

            @if (companyLocked()) {
              <button class="btn secondary-btn" type="button" (click)="resetCompanySearch()">
                Cambiar empresa / Limpiar
              </button>
            }
          </div>

          @if (lookup(); as companyLookup) {
            <article
              class="verification"
              [class.good]="companyLookup.state === 'VERIFIED'"
              [class.pending]="companyLookup.state === 'PENDING'"
              [class.bad]="companyLookup.state === 'REVIEW_REQUIRED'"
            >
              <div class="verification-head">
                <strong>{{ verificationTitle(companyLookup) }}</strong>
                <span class="badge">{{ companyLookup.state }}</span>
              </div>
              <p>{{ companyLookup.message }}</p>

              @if (companyLookup.platform.alreadyRegistered) {
                <p class="platform-warning">
                  Esta organización ya está registrada en Librería Inglés. No se puede iniciar un alta duplicada.
                </p>
              } @else if (companyLookup.platform.onboardingInProgress) {
                <div class="platform-warning stack-small">
                  <span>Ya existe una solicitud de alta en curso para esta organización.</span>
                  @if (config()?.devPurgeAllowed) {
                    <button
                      class="btn danger-btn"
                      type="button"
                      (click)="purgeCurrentOnboarding()"
                      [disabled]="purgeBusy()"
                    >
                      {{ purgeBusy() ? 'Eliminando…' : 'DEV · Eliminar alta incompleta por CUIT' }}
                    </button>
                  }
                </div>
              }

              @if (companyLookup.developmentSimulation) {
                <p class="dev-warning">
                  DEV · Los datos empresariales son simulados para probar el flujo. No provienen de ARCA/RNS.
                </p>
              }

              @if (companyLookup.company.legalName) {
                <dl class="company-data">
                  <div><dt>Razón social</dt><dd>{{ companyLookup.company.legalName }}</dd></div>
                  <div><dt>Tipo</dt><dd>{{ companyLookup.company.legalEntityType || '—' }}</dd></div>
                  <div><dt>Jurisdicción</dt><dd>{{ companyLookup.company.registryJurisdiction || '—' }}</dd></div>
                  <div><dt>Registro</dt><dd>{{ companyLookup.company.registryNumber || '—' }}</dd></div>
                  <div><dt>Domicilio fiscal</dt><dd>{{ companyLookup.company.fiscalAddress || '—' }}</dd></div>
                  <div><dt>Actividad</dt><dd>{{ companyLookup.company.primaryActivity || '—' }}</dd></div>
                </dl>
              }
            </article>
          }
        </section>

        @if (canContinueWithCompany()) {
          <section class="panel stack">
            <div>
              <p class="step">Paso 2</p>
              <h2>Datos complementarios</h2>
            </div>

            <div class="grid two">
              <label class="field">
                Nombre visible / de fantasía (editable)
                <input class="input" name="displayName" [(ngModel)]="displayName" maxlength="120" />
                <span class="field-help">
                  Se precarga con la razón social cuando está disponible. Cambialo si la empresa usa otra marca.
                </span>
              </label>
              <label class="field">
                Sitio web (opcional)
                <input class="input" name="website" [(ngModel)]="website" placeholder="https://empresa.com" />
                <span class="field-help">
                  El RNS no informa el sitio web. Completalo si lo conocés; más adelante servirá para branding.
                </span>
              </label>
            </div>
          </section>

          <section class="panel stack">
            <div>
              <p class="step">Paso 3</p>
              <h2>Persona referente</h2>
              <p class="muted">
                Esta persona inicia el alta. Su email se verificará en P02; todavía no se crea una cuenta
                corporativa ni un ADMIN.
              </p>
            </div>

            <div class="grid two">
              <label class="field">
                Nombre
                <input class="input" name="firstName" [(ngModel)]="firstName" autocomplete="given-name" />
              </label>
              <label class="field">
                Apellido
                <input class="input" name="lastName" [(ngModel)]="lastName" autocomplete="family-name" />
              </label>
            </div>

            <div class="grid two">
              <label class="field">
                Email
                <input class="input" type="email" name="email" [(ngModel)]="email" autocomplete="email" />
              </label>
              <label class="field">
                Celular / teléfono
                <input class="input" name="phone" [(ngModel)]="phone" autocomplete="tel" />
              </label>
            </div>

            <div class="grid two">
              <div class="field">
                <label for="jobTitle">Cargo o función</label>
                <input
                  id="jobTitle"
                  class="input"
                  name="jobTitle"
                  [(ngModel)]="jobTitle"
                  (ngModelChange)="onJobTitleInput($event)"
                  (focus)="loadJobTitleSuggestions()"
                  placeholder="Ej. Responsable de Capacitación"
                  autocomplete="off"
                />

                @if (jobTitleId !== null) {
                  <span class="catalog-selected">Seleccionado del catálogo.</span>
                }

                @if (jobTitleSuggestions().length > 0 && jobTitleId === null) {
                  <div class="catalog-options">
                    @for (item of jobTitleSuggestions(); track item.id) {
                      <button
                        class="catalog-option"
                        type="button"
                        (click)="selectJobTitle(item)"
                      >
                        {{ item.name }}
                      </button>
                    }
                  </div>
                }

                @if (jobTitle.trim().length >= 2 && jobTitleId === null) {
                  <button
                    class="btn secondary-btn compact"
                    type="button"
                    (click)="resolveJobTitle(false)"
                    [disabled]="jobTitleResolveBusy()"
                  >
                    {{ jobTitleResolveBusy() ? 'Revisando…' : 'Agregar / validar cargo' }}
                  </button>
                }

                @if (jobTitleSimilar().length > 0) {
                  <div class="similar-warning">
                    <strong>Encontramos cargos parecidos.</strong>
                    <span>Elegí uno para evitar duplicados o confirmá que querés crear uno nuevo.</span>
                    <div class="catalog-options">
                      @for (item of jobTitleSimilar(); track item.id) {
                        <button
                          class="catalog-option"
                          type="button"
                          (click)="selectJobTitle(item)"
                        >
                          {{ item.name }}
                        </button>
                      }
                    </div>
                    <button
                      class="btn secondary-btn compact"
                      type="button"
                      (click)="resolveJobTitle(true)"
                      [disabled]="jobTitleResolveBusy()"
                    >
                      Crear "{{ jobTitle }}" igualmente
                    </button>
                  </div>
                }
              </div>
              <label class="field">
                Carácter en que actúa
                <select class="input" name="actingCapacity" [(ngModel)]="actingCapacity">
                  @for (item of config()?.actingCapacities ?? []; track item.code) {
                    <option [value]="item.code">{{ item.name }}</option>
                  }
                </select>
              </label>
            </div>

            <label class="authority">
              <input type="checkbox" name="authorityDeclared" [(ngModel)]="authorityDeclared" />
              <span>
                Declaro contar con autorización suficiente para iniciar el alta del servicio en representación
                de esta organización.
              </span>
            </label>

            <button
              class="btn primary"
              type="button"
              (click)="save()"
              [disabled]="saveBusy() || result() !== null || !canSave()"
            >
              {{
                result()
                  ? 'Solicitud guardada'
                  : saveBusy()
                    ? 'Guardando…'
                    : 'Guardar solicitud de alta'
              }}
            </button>
          </section>
        }

        @if (result(); as saved) {
          <section class="panel result">
            <p class="step">P01 guardado</p>
            <h2>Solicitud registrada</h2>
            <p>
              Estado: <strong>{{ saved.status }}</strong>. Identificador:
              <code>{{ saved.publicId }}</code>.
            </p>
            @if (saved.nextStep === 'EMAIL_VERIFICATION_PENDING_P02') {
              <p>La empresa quedó validada para este entorno. El próximo corte será verificar el email del referente (P02).</p>
            } @else if (saved.nextStep === 'COMPANY_VERIFICATION_PENDING') {
              <p>La solicitud quedó guardada y espera verificación empresarial oficial.</p>
            } @else {
              <p>La solicitud requiere revisión antes de continuar.</p>
            }

            @if (config()?.devPurgeAllowed) {
              <button
                class="btn danger-btn"
                type="button"
                (click)="purgeCurrentOnboarding()"
                [disabled]="purgeBusy()"
              >
                {{ purgeBusy() ? 'Eliminando…' : 'DEV · Eliminar esta alta por CUIT' }}
              </button>
            }
          </section>
        }

        @if (notice()) {
          <p class="notice">{{ notice() }}</p>
        }

        @if (error()) {
          <p class="error">{{ error() }}</p>
        }
      }
    </main>
  `,
  styles: `
    :host { display: block; }
    .onboarding { min-height: 100vh; max-width: 980px; margin: 0 auto; padding: 0 1.25rem 5rem; }
    .topbar { min-height: 5rem; display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
    .brand, .back { color: inherit; text-decoration: none; }
    .brand { font-weight: 750; font-size: 1.15rem; }
    .back { font-size: 0.9rem; }
    .heading { max-width: 760px; margin: 3rem 0 2rem; }
    .heading h1 { margin: 0.35rem 0 0.8rem; font-size: clamp(2.3rem, 6vw, 4.2rem); letter-spacing: -0.045em; }
    .heading p { line-height: 1.6; }
    .eyebrow, .step { margin: 0; text-transform: uppercase; letter-spacing: 0.11em; font-size: 0.76rem; font-weight: 750; }
    .panel { margin-top: 1rem; padding: 1.4rem; border: 1px solid #ddd; border-radius: 1rem; background: #fff; }
    .stack { display: grid; gap: 1rem; }
    .grid { display: grid; gap: 1rem; }
    .grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    h2 { margin: 0.3rem 0; }
    .muted { color: #666; line-height: 1.5; }
    .field { display: grid; gap: 0.4rem; font-size: 0.9rem; font-weight: 650; }
    .field-help { color: #666; font-size: 0.76rem; font-weight: 400; line-height: 1.35; }
    .input { width: 100%; box-sizing: border-box; padding: 0.78rem 0.85rem; border: 1px solid #bbb; border-radius: 0.65rem; font: inherit; background: #fff; }
    .btn { width: fit-content; border-radius: 0.7rem; padding: 0.8rem 1.1rem; font: inherit; font-weight: 700; cursor: pointer; }
    .btn.primary { border: 1px solid #111; background: #111; color: #fff; }
    .btn.secondary-btn { border: 1px solid #bbb; background: #fff; color: #111; }
    .btn.danger-btn { border: 1px solid #b45a54; background: #fff; color: #8f1e18; }
    .btn:disabled { cursor: not-allowed; opacity: 0.5; }
    .search-actions { display: flex; gap: 0.75rem; flex-wrap: wrap; }
    .compact { padding: 0.55rem 0.75rem; font-size: 0.82rem; }
    .catalog-options { display: flex; gap: 0.45rem; flex-wrap: wrap; }
    .catalog-option { border: 1px solid #bbb; border-radius: 999px; padding: 0.35rem 0.6rem; background: #fff; cursor: pointer; font: inherit; font-size: 0.8rem; }
    .catalog-option:hover { border-color: #111; }
    .catalog-selected { color: #285f3c; font-size: 0.78rem; font-weight: 650; }
    .similar-warning { display: grid; gap: 0.55rem; padding: 0.75rem; border-radius: 0.65rem; background: #fff8e8; color: #735200; font-size: 0.8rem; font-weight: 500; }
    .verification { padding: 1rem; border: 1px solid #bbb; border-radius: 0.8rem; }
    .verification.good { border-color: #55966f; background: #f4fbf6; }
    .verification.pending { border-color: #b79755; background: #fffaf0; }
    .verification.bad { border-color: #b45a54; background: #fff6f5; }
    .verification-head { display: flex; justify-content: space-between; gap: 1rem; }
    .badge { font-size: 0.72rem; padding: 0.2rem 0.45rem; border: 1px solid currentColor; border-radius: 999px; }
    .dev-warning { padding: 0.7rem; border-radius: 0.6rem; background: #fff0c7; font-size: 0.85rem; font-weight: 650; }
    .platform-warning { padding: 0.7rem; border-radius: 0.6rem; background: #fff1f0; color: #8f1e18; font-size: 0.9rem; font-weight: 700; }
    .stack-small { display: grid; gap: 0.65rem; justify-items: start; }
    .company-data { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.8rem 1rem; margin: 1rem 0 0; }
    .company-data div { min-width: 0; }
    dt { font-size: 0.75rem; color: #666; }
    dd { margin: 0.15rem 0 0; overflow-wrap: anywhere; }
    .authority { display: flex; gap: 0.75rem; align-items: flex-start; line-height: 1.45; }
    .authority input { margin-top: 0.25rem; }
    .result { border-color: #55966f; background: #f4fbf6; }
    .notice { margin-top: 1rem; padding: 0.9rem; border-radius: 0.7rem; color: #285f3c; background: #f1faf4; }
    .error { margin-top: 1rem; padding: 0.9rem; border-radius: 0.7rem; color: #8f1e18; background: #fff1f0; }
    @media (max-width: 700px) {
      .grid.two, .company-data { grid-template-columns: 1fr; }
      .heading { margin-top: 1.5rem; }
      .topbar { align-items: flex-start; padding: 1rem 0; }
    }
  `
})
export class OrganizationOnboardingComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly config = signal<OrganizationOnboardingConfig | null>(null);
  readonly lookup = signal<OrganizationCompanyLookupResult | null>(null);
  readonly result = signal<OrganizationOnboardingResult | null>(null);
  readonly loading = signal(true);
  readonly lookupBusy = signal(false);
  readonly saveBusy = signal(false);
  readonly purgeBusy = signal(false);
  readonly jobTitleBusy = signal(false);
  readonly jobTitleResolveBusy = signal(false);
  readonly jobTitleSuggestions = signal<JobTitleOption[]>([]);
  readonly jobTitleSimilar = signal<JobTitleOption[]>([]);
  readonly notice = signal<string | null>(null);
  readonly error = signal<string | null>(null);

  country = 'AR';
  taxIdType = 'CUIT';
  taxId = '';
  displayName = '';
  website = '';

  firstName = '';
  lastName = '';
  email = '';
  phone = '';
  jobTitle = '';
  jobTitleId: number | null = null;
  private jobTitleTimer: ReturnType<typeof setTimeout> | null = null;
  actingCapacity: OrganizationActingCapacity = 'AUTHORIZED_EMPLOYEE';
  authorityDeclared = false;

  async ngOnInit(): Promise<void> {
    try {
      this.config.set(await firstValueFrom(this.api.organizationOnboardingConfig()));
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo cargar la configuración del alta corporativa.'));
    } finally {
      this.loading.set(false);
    }
  }

  resetLookup(): void {
    if (this.companyLocked()) {
      return;
    }
    this.lookup.set(null);
    this.result.set(null);
    this.error.set(null);
  }

  companyLocked(): boolean {
    const value = this.lookup();
    return Boolean(value?.state === 'VERIFIED' && value.company.legalName);
  }

  canContinueWithCompany(): boolean {
    const value = this.lookup();
    return Boolean(
      value &&
      value.state !== 'REVIEW_REQUIRED' &&
      !value.platform.alreadyRegistered &&
      !value.platform.onboardingInProgress
    );
  }

  resetCompanySearch(): void {
    this.lookup.set(null);
    this.result.set(null);
    this.taxId = '';
    this.displayName = '';
    this.website = '';
    this.notice.set(null);
    this.error.set(null);
  }

  async purgeCurrentOnboarding(): Promise<void> {
    if (!this.taxId.trim() || !this.config()?.devPurgeAllowed) {
      return;
    }
    this.purgeBusy.set(true);
    this.error.set(null);
    this.notice.set(null);
    const taxId = this.taxId;
    try {
      const response = await firstValueFrom(
        this.api.purgeOrganizationOnboardingDev(
          this.country,
          this.taxIdType,
          taxId
        )
      );
      this.resetCompanySearch();
      this.notice.set(
        response.deletedOnboardings > 0
          ? `DEV · Se eliminaron ${response.deletedOnboardings} alta(s) incompleta(s) para el CUIT ${taxId}.`
          : `DEV · No había altas incompletas para el CUIT ${taxId}.`
      );
    } catch (err) {
      this.error.set(
        errorMessage(err, 'No se pudo eliminar el alta incompleta.')
      );
    } finally {
      this.purgeBusy.set(false);
    }
  }

  async lookupCompany(): Promise<void> {
    if (this.companyLocked()) {
      return;
    }
    this.lookupBusy.set(true);
    this.notice.set(null);
    this.error.set(null);
    this.result.set(null);
    try {
      const found = await firstValueFrom(
        this.api.lookupOrganizationCompany({
          country: this.country,
          taxIdType: this.taxIdType,
          taxId: this.taxId
        })
      );
      this.lookup.set(found);
      if (!this.displayName.trim() && found.company.legalName) {
        this.displayName = found.company.legalName;
      }
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo consultar la empresa.'));
    } finally {
      this.lookupBusy.set(false);
    }
  }

  onJobTitleInput(value: string): void {
    this.jobTitle = value;
    this.jobTitleId = null;
    this.jobTitleSimilar.set([]);

    if (this.jobTitleTimer !== null) {
      clearTimeout(this.jobTitleTimer);
    }
    if (value.trim().length < 2) {
      this.jobTitleSuggestions.set([]);
      return;
    }
    this.jobTitleTimer = setTimeout(() => {
      void this.loadJobTitleSuggestions();
    }, 250);
  }

  async loadJobTitleSuggestions(): Promise<void> {
    if (this.jobTitleBusy()) return;
    this.jobTitleBusy.set(true);
    try {
      const rows = await firstValueFrom(
        this.api.organizationJobTitles(this.jobTitle.trim(), 8)
      );
      this.jobTitleSuggestions.set(
        rows.filter((item) => item.id !== this.jobTitleId)
      );
    } catch {
      this.jobTitleSuggestions.set([]);
    } finally {
      this.jobTitleBusy.set(false);
    }
  }

  selectJobTitle(item: JobTitleOption): void {
    this.jobTitleId = item.id;
    this.jobTitle = item.name;
    this.jobTitleSuggestions.set([]);
    this.jobTitleSimilar.set([]);
  }

  async resolveJobTitle(confirmSimilar: boolean): Promise<boolean> {
    const value = this.jobTitle.trim();
    if (value.length < 2) return false;

    this.jobTitleResolveBusy.set(true);
    this.error.set(null);
    try {
      const response = await firstValueFrom(
        this.api.resolveOrganizationJobTitle(value, confirmSimilar)
      );
      if (response.status === 'SIMILAR') {
        this.jobTitleSimilar.set(response.similar);
        return false;
      }
      if (response.item) {
        this.selectJobTitle(response.item);
        return true;
      }
      return false;
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo validar el cargo o función.'));
      return false;
    } finally {
      this.jobTitleResolveBusy.set(false);
    }
  }

  async ensureJobTitle(): Promise<boolean> {
    if (this.jobTitleId !== null) {
      return true;
    }
    return this.resolveJobTitle(false);
  }

  verificationTitle(value: OrganizationCompanyLookupResult): string {
    if (value.state === 'VERIFIED') return 'Empresa localizada';
    if (value.state === 'PENDING') return 'Verificación oficial pendiente';
    return 'Revisá el CUIT';
  }

  canSave(): boolean {
    if (this.result() !== null) {
      return false;
    }
    return Boolean(
      this.canContinueWithCompany() &&
      this.firstName.trim() &&
      this.lastName.trim() &&
      this.email.trim() &&
      this.phone.trim() &&
      this.jobTitle.trim() &&
      this.actingCapacity &&
      this.authorityDeclared
    );
  }

  async save(): Promise<void> {
    if (this.result() !== null || !this.canSave()) return;
    if (!(await this.ensureJobTitle())) {
      return;
    }
    this.saveBusy.set(true);
    this.error.set(null);
    try {
      this.result.set(
        await firstValueFrom(
          this.api.createOrganizationOnboarding({
            country: this.country,
            taxIdType: this.taxIdType,
            taxId: this.taxId,
            displayName: this.displayName.trim() || null,
            website: this.website.trim() || null,
            referent: {
              firstName: this.firstName.trim(),
              lastName: this.lastName.trim(),
              email: this.email.trim(),
              jobTitleId: this.jobTitleId,
              jobTitle: this.jobTitle.trim(),
              phone: this.phone.trim(),
              actingCapacity: this.actingCapacity,
              authorityDeclared: this.authorityDeclared
            }
          })
        )
      );
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo guardar la solicitud de alta.'));
    } finally {
      this.saveBusy.set(false);
    }
  }
}
