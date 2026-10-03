import { Component, EventEmitter, Input, Output } from '@angular/core';

@Component({
  selector: 'app-active-toggle',
  template: `
    <div class="state-toggle" role="group" aria-label="Estado">
      <button
        class="btn btn-sm"
        type="button"
        [class.btn-primary]="value"
        [attr.aria-pressed]="value"
        [disabled]="disabled"
        (click)="set(true)">
        Activo
      </button>
      <button
        class="btn btn-sm"
        type="button"
        [class.selected-off]="!value"
        [attr.aria-pressed]="!value"
        [disabled]="disabled"
        (click)="set(false)">
        Inactivo
      </button>
    </div>
  `,
  styles: `
    .state-toggle {
      display: inline-flex;
      gap: 0.25rem;
      padding: 0.2rem;
      border: 1px solid var(--border);
      border-radius: 0.55rem;
      background: var(--bg);
    }
    .state-toggle .btn {
      min-width: 5.2rem;
    }
    .selected-off {
      font-weight: 700;
      background: var(--border);
    }
  `
})
export class ActiveToggleComponent {
  @Input() value = true;
  @Input() disabled = false;
  @Output() readonly valueChange = new EventEmitter<boolean>();

  set(next: boolean): void {
    if (next === this.value) return;
    this.value = next;
    this.valueChange.emit(next);
  }
}
