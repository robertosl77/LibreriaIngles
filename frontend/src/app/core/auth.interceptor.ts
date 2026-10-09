import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const token = auth.token();
  const isApi = request.url.startsWith(environment.apiUrl);

  const headers: Record<string, string> = {};
  if (token && isApi) {
    headers['Authorization'] = `Bearer ${token}`;
    // T-220 (E-01): empresa en la que actúa la sesión; el backend la valida contra la membresía.
    const organizationId = auth.organizationId();
    if (organizationId !== null) {
      headers['X-Organization-Id'] = String(organizationId);
    }
  }
  const authorized = Object.keys(headers).length ? request.clone({ setHeaders: headers }) : request;

  return next(authorized).pipe(
    catchError((error: unknown) => {
      const isAuthCall = request.url.includes('/auth/');
      if (error instanceof HttpErrorResponse && error.status === 401 && isApi && !isAuthCall) {
        auth.logout();
      }
      return throwError(() => error);
    })
  );
};
