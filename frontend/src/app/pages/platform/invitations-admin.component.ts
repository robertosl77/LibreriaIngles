import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiService, errorMessage } from '../../core/api.service';
import {
  InvitationRecipientMode,
  InvitationStatus,
  PlatformBenefit,
  PlatformInvitation,
  PlatformInvitationDraft
} from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CollapseCardComponent } from '../../shared/ui/collapse-card.component';

interface InvitationForm {
  name: string;
  benefitId: number | null;
  recipientMode: InvitationRecipientMode;
  email: string;
  firstName: string;
  lastName: string;
  maxRedemptions: number;
  expiresAt: string;
}

function emptyForm(benefitId: number | null): InvitationForm {
  return {
    name: '',
    benefitId,
    recipientMode: 'NAMED',
    email: '',
    firstName: '',
    lastName: '',
    maxRedemptions: 1,
    expiresAt: ''
  };
}

function isoDate(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

@Component({
  selector: 'app-invitations-admin',
  imports: [FormsModule, DatePipe, CollapseCardComponent],
  template: `
    <app-collapse-card
      title="Pre-invitaciones e invitaciones"
      description="Nominada = identidad concreta. Abierta = cualquiera con el link hasta el cupo configurado. El beneficio se define una sola vez."
    >
      @if (!creating()) {
        <div class="collapse-actions">
          <button class="btn btn-sm" type="button" (click)="startNew()">Nueva invitación</button>
        </div>
      }

      @if (creating()) {
        <form class="editor stack" (ngSubmit)="save()">
          <div class="grid">
            <label class="field">
              Nombre interno
              <input class="input" name="iName" [(ngModel)]="form.name" required maxlength="120"
                placeholder="Ej. Regalo amigo / Equipo octubre" />
            </label>
            <label class="field">
              Beneficio
              <select class="input" name="iBenefit" [(ngModel)]="form.benefitId" required>
                @for (benefit of activeBenefits(); track benefit.id) {
                  <option [ngValue]="benefit.id">
                    {{ benefit.name }} · {{ benefit.serviceName }}
                  </option>
                }
              </select>
            </label>
            <label class="field">
              Tipo
              <select class="input" name="iMode" [(ngModel)]="form.recipientMode">
                <option value="NAMED">Nominada · persona concreta</option>
                <option value="OPEN">Abierta · quien tenga el link</option>
              </select>
            </label>
            <label class="field">
              Vence el link (opcional)
              <input class="input" type="datetime-local" name="iExpires" [(ngModel)]="form.expiresAt" />
            </label>
          </div>

          @if (form.recipientMode === 'NAMED') {
            <div class="grid">
              <label class="field">
                Email
                <input class="input" type="email" name="iEmail" [(ngModel)]="form.email" required />
              </label>
              <label class="field">
                Nombre (opcional)
                <input class="input" name="iFirst" [(ngModel)]="form.firstName" maxlength="100" />
              </label>
              <label class="field">
                Apellido (opcional)
                <input class="input" name="iLast" [(ngModel)]="form.lastName" maxlength="100" />
              </label>
            </div>
            <p class="banner small">
              Esta invitación queda en cola de email (<strong>PENDING</strong>). T-051 hará el envío
              automático; hasta entonces el link puede copiarse manualmente como respaldo.
            </p>
          } @else {
            <label class="field narrow">
              Cantidad máxima de canjes
              <input class="input" type="number" min="1" name="iMax" [(ngModel)]="form.maxRedemptions" />
              <span class="muted tiny">1 = regalo transferible de un solo uso. N = primeras N cuentas distintas.</span>
            </label>
          }

          <div class="row">
            <button class="btn btn-primary btn-sm" type="submit"
              [disabled]="saving() || !canSave()">
              @if (saving()) { <span class="spinner"></span> } Generar invitación
            </button>
            <button class="btn btn-sm" type="button" (click)="creating.set(false)">Cancelar</button>
          </div>
        </form>
      }

      @if (loading()) {
        <p class="muted"><span class="spinner"></span></p>
      } @else if (invitations().length === 0) {
        <p class="muted">Todavía no hay invitaciones.</p>
      } @else {
        <div class="invite-list">
          @for (invite of invitations(); track invite.id) {
            <article class="invite" [class.dim]="invite.status !== 'ACTIVE'">
              <div class="stack compact">
                <div class="row">
                  <strong>{{ invite.name }}</strong>
                  <span [class]="statusClass(invite.status)">{{ statusLabel(invite.status) }}</span>
                  <span class="chip">{{ invite.recipientMode === 'NAMED' ? 'Nominada' : 'Abierta' }}</span>
                </div>
                <div class="small">
                  <strong>{{ invite.benefitName }}</strong> · {{ invite.serviceName }}
                  @if (invite.durationDays) { · {{ invite.durationDays }} días }
                </div>
                @if (invite.recipientMode === 'NAMED') {
                  <div class="small">
                    {{ invite.firstName }} {{ invite.lastName }} &lt;{{ invite.email }}&gt;
                    @if (invite.emailStatus) { · email {{ invite.emailStatus }} }
                  </div>
                } @else {
                  <div class="small">
                    {{ invite.redemptions }} / {{ invite.maxRedemptions }} canje(s)
                    · quedan {{ invite.remaining }}
                  </div>
                }
                <div class="muted small">
                  @if (invite.expiresAt) { Vence {{ invite.expiresAt | date: 'dd/MM/yyyy HH:mm' }} }
                  @else { Link sin vencimiento configurado }
                </div>
              </div>
              <div class="actions row">
                @if (invite.token) {
                  <button class="btn btn-sm" type="button" (click)="copy(invite)">Copiar link</button>
                }
                @if (invite.status === 'ACTIVE') {
                  <button class="btn btn-sm" type="button" (click)="regenerate(invite)">Regenerar link</button>
                  <button class="btn btn-sm btn-danger" type="button" (click)="cancel(invite)">Anular</button>
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
    .editor { padding: 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; background: var(--bg); }
    .narrow { max-width: 18rem; }
    .invite-list { display: flex; flex-direction: column; gap: 0.6rem; }
    .invite { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; padding: 0.8rem; border: 1px solid var(--border); border-radius: 0.6rem; }
    .compact { gap: 0.3rem; }
    .dim { opacity: 0.7; }
    .tiny { font-size: 0.76rem; }
    @media (max-width: 760px) {
      .invite { flex-direction: column; }
    }
  `
})
export class InvitationsAdminComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly toast = inject(ToastService);

  readonly invitations = signal<PlatformInvitation[]>([]);
  readonly benefits = signal<PlatformBenefit[]>([]);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly creating = signal(false);
  readonly activeBenefits = computed(() => this.benefits().filter((benefit) => benefit.active));

  form: InvitationForm = emptyForm(null);

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  async load(): Promise<void> {
    this.loading.set(true);
    try {
      const [invitations, benefits] = await Promise.all([
        firstValueFrom(this.api.platformInvitations()),
        firstValueFrom(this.api.platformBenefits())
      ]);
      this.invitations.set(invitations);
      this.benefits.set(benefits);
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  startNew(): void {
    this.form = emptyForm(this.activeBenefits()[0]?.id ?? null);
    this.creating.set(true);
  }

  canSave(): boolean {
    return !!this.form.name.trim()
      && !!this.form.benefitId
      && (this.form.recipientMode === 'OPEN' || !!this.form.email.trim());
  }

  async save(): Promise<void> {
    if (!this.form.benefitId) return;
    const draft: PlatformInvitationDraft = {
      name: this.form.name.trim(),
      benefitId: this.form.benefitId,
      recipientMode: this.form.recipientMode,
      email: this.form.recipientMode === 'NAMED' ? this.form.email.trim().toLowerCase() : null,
      firstName: this.form.recipientMode === 'NAMED' ? this.form.firstName.trim() || null : null,
      lastName: this.form.recipientMode === 'NAMED' ? this.form.lastName.trim() || null : null,
      maxRedemptions: this.form.recipientMode === 'NAMED'
        ? 1
        : Math.max(1, Math.round(Number(this.form.maxRedemptions) || 1)),
      expiresAt: isoDate(this.form.expiresAt)
    };

    this.saving.set(true);
    try {
      const created = await firstValueFrom(this.api.createPlatformInvitation(draft));
      this.toast.success('Invitación generada.');
      this.creating.set(false);
      await this.load();
      if (created.token) {
        await this.copy(created);
      }
    } catch (err) {
      this.toast.error(errorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }

  link(invite: PlatformInvitation): string | null {
    return invite.token
      ? `${window.location.origin}/invitacion/${encodeURIComponent(invite.token)}`
      : null;
  }

  async copy(invite: PlatformInvitation): Promise<void> {
    const link = this.link(invite);
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      this.toast.success('Link de invitación copiado.');
    } catch {
      this.toast.error('No se pudo copiar el link.');
    }
  }

  async regenerate(invite: PlatformInvitation): Promise<void> {
    if (!confirm('¿Regenerar el link? El link anterior dejará de funcionar.')) return;
    try {
      const updated = await firstValueFrom(this.api.regeneratePlatformInvitation(invite.id));
      this.replace(updated);
      await this.copy(updated);
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }

  async cancel(invite: PlatformInvitation): Promise<void> {
    if (!confirm(`¿Anular la invitación "${invite.name}"?`)) return;
    try {
      this.replace(await firstValueFrom(this.api.cancelPlatformInvitation(invite.id)));
      this.toast.success('Invitación anulada.');
    } catch (err) {
      this.toast.error(errorMessage(err));
    }
  }

  private replace(updated: PlatformInvitation): void {
    this.invitations.update((rows) => rows.map((row) => row.id === updated.id ? updated : row));
  }

  statusLabel(status: InvitationStatus): string {
    return {
      ACTIVE: 'Activa',
      CANCELLED: 'Anulada',
      EXPIRED: 'Vencida',
      EXHAUSTED: 'Sin cupo'
    }[status];
  }

  statusClass(status: InvitationStatus): string {
    return status === 'ACTIVE' ? 'chip chip-ok' : status === 'EXHAUSTED' ? 'chip chip-warn' : 'chip';
  }
}
