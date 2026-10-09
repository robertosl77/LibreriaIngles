import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../environments/environment';

/** Nombre por defecto mientras responde el backend (o si no responde). */
const FALLBACK_BRAND = 'Librería Inglés';

/**
 * T-220 (E-13): marca del producto en un solo lugar. Viene del backend (BRAND_NAME), así cambiar
 * de producto o de cliente no obliga a tocar cada pantalla.
 */
@Injectable({ providedIn: 'root' })
export class BrandService {
  private readonly http = inject(HttpClient);

  readonly name = signal(FALLBACK_BRAND);

  async load(): Promise<void> {
    try {
      const branding = await firstValueFrom(
        this.http.get<{ name: string }>(`${environment.apiUrl}/system/branding`)
      );
      if (branding?.name) {
        this.name.set(branding.name);
      }
    } catch {
      // Sin backend la app sigue con la marca por defecto.
    }
  }
}

/** Títulos de pestaña: "<título de la ruta> · <marca>", o solo la marca. */
@Injectable({ providedIn: 'root' })
export class BrandTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);
  private readonly brand = inject(BrandService);

  override updateTitle(snapshot: RouterStateSnapshot): void {
    const page = this.buildTitle(snapshot);
    const brand = this.brand.name();
    this.title.setTitle(page ? `${page} · ${brand}` : brand);
  }
}
