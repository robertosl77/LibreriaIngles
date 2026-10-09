import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { inject, provideAppInitializer, provideZoneChangeDetection } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { TitleStrategy, provideRouter, withComponentInputBinding } from '@angular/router';

import { AppComponent } from './app/app.component';
import { routes } from './app/app.routes';
import { authInterceptor } from './app/core/auth.interceptor';
import { BrandService, BrandTitleStrategy } from './app/core/brand.service';

bootstrapApplication(AppComponent, {
  providers: [
    // Angular 21 usa "zoneless" por defecto; la app sigue con zone.js (T-002).
    provideZoneChangeDetection(),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideRouter(routes, withComponentInputBinding()),
    // T-220 (E-13): la marca llega del backend antes de pintar la primera pantalla.
    provideAppInitializer(() => inject(BrandService).load()),
    { provide: TitleStrategy, useClass: BrandTitleStrategy }
  ]
}).catch((error) => console.error(error));
