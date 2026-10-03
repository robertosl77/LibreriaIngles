import { Component, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

export interface TabNavItem {
  label: string;
  route: string;
}

@Component({
  selector: 'app-tab-nav',
  imports: [RouterLink, RouterLinkActive],
  template: `
    <nav class="tab-nav" [attr.aria-label]="ariaLabel()">
      @for (item of items(); track item.route) {
        <a
          [routerLink]="item.route"
          routerLinkActive="active"
          [routerLinkActiveOptions]="{ exact: true }"
        >
          {{ item.label }}
        </a>
      }
    </nav>
  `,
  styles: `
    .tab-nav {
      display: flex;
      gap: 0.2rem;
      border-bottom: 1px solid var(--border);
      overflow-x: auto;
    }

    .tab-nav a {
      padding: 0.55rem 0.85rem 0.65rem;
      color: var(--muted);
      font-weight: 650;
      text-decoration: none;
      white-space: nowrap;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: color 0.15s ease, border-color 0.15s ease;
    }

    .tab-nav a:hover { color: inherit; }

    .tab-nav a.active {
      color: inherit;
      border-bottom-color: var(--accent);
    }

    @media (prefers-reduced-motion: reduce) {
      .tab-nav a { transition: none; }
    }
  `
})
export class TabNavComponent {
  readonly items = input.required<TabNavItem[]>();
  readonly ariaLabel = input('Secciones');
}
