import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const token = auth.token();
  const isApi = request.url.startsWith(environment.apiUrl);

  const authorized =
    token && isApi ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : request;

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
