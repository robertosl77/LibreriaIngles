import { Component, computed, input, model, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ModelOption } from '../core/models';

/**
 * Selector de modelo: lista obtenida del proveedor, con opción de escribirlo a mano.
 * Si el modelo actual no figura en la lista, lo avisa (probablemente discontinuado).
 */
@Component({
  selector: 'app-model-picker',
  imports: [FormsModule],
  template: `
    <div class="picker">
      @if (loading()) {
        <div class="input loading"><span class="spinner"></span> Buscando modelos…</div>
      } @else if (options()?.length && !manual()) {
        <select class="input" [ngModel]="value()" (ngModelChange)="onSelect($event)" [attr.name]="name()">
          @if (!value()) {
            <option value="" disabled>Elegí un modelo</option>
          }
          @if (value() && !inList()) {
            <option [value]="value()">{{ value() }} (no está en la lista)</option>
          }
          @for (option of options(); track option.id) {
            <option [value]="option.id">{{ option.label === option.id ? option.id : option.label + ' · ' + option.id }}</option>
          }
          <option [value]="MANUAL">Escribir otro…</option>
        </select>
      } @else {
        <input class="input" [attr.name]="name()" [ngModel]="value()" (ngModelChange)="value.set($event)"
          [placeholder]="placeholder()" autocomplete="off" spellcheck="false" />
      }

      @if (!loading()) {
        @if (value() && options()?.length && !inList() && !manual()) {
          <span class="small warn">Este modelo no figura en tu cuenta del proveedor: puede estar discontinuado.</span>
        }
        @if (error()) {
          <span class="small muted">{{ error() }} Podés escribirlo a mano.</span>
        } @else if (!options()) {
          <span class="small muted">{{ hint() }}</span>
        }
        @if (manual() && options()?.length) {
          <button class="btn-link small" type="button" (click)="manual.set(false)">Elegir de la lista</button>
        }
        @if (canRefresh()) {
          <button class="btn-link small" type="button" (click)="refresh.emit()">
            {{ options() ? 'Actualizar lista' : 'Buscar modelos del proveedor' }}
          </button>
        }
      }
    </div>
  `,
  styles: `
    .picker { display: flex; flex-direction: column; gap: 0.3rem; align-items: flex-start; }
    .picker .input { width: 100%; }
    .loading { display: flex; align-items: center; gap: 0.5rem; color: var(--muted); }
    .warn { color: var(--warn); }
  `
})
export class ModelPickerComponent {
  readonly MANUAL = '__manual__';

  readonly value = model<string>('');
  readonly options = input<ModelOption[] | null>(null);
  readonly loading = input(false);
  readonly error = input<string | null>(null);
  readonly placeholder = input('');
  readonly name = input('model');
  readonly hint = input('La lista de modelos se consulta al proveedor con la API key.');
  readonly canRefresh = input(true);
  readonly refresh = output<void>();

  readonly manual = signal(false);
  readonly inList = computed(() => (this.options() ?? []).some((o) => o.id === this.value()));

  onSelect(selected: string): void {
    if (selected === this.MANUAL) {
      this.manual.set(true);
      return;
    }
    this.value.set(selected);
  }
}
