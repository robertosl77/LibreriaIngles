import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

/**
 * Solo exige sesión. No bloquea la navegación por pasos pendientes (nivel, IA):
 * esos se muestran como "Primeros pasos" en el inicio.
 */
export const authGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isLoggedIn()) {
    return router.createUrlTree(['/login']);
  }

  try {
    if (!auth.me()) {
      await auth.refreshMe();
    }
    return true;
  } catch {
    auth.logout(false);
    return router.createUrlTree(['/login']);
  }
};

export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  return auth.isLoggedIn() ? inject(Router).createUrlTree(['/app']) : true;
};

export const platformOwnerGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  try {
    const me = auth.me() ?? (await auth.refreshMe());
    return me.account.isPlatformOwner ? true : router.createUrlTree(['/app']);
  } catch {
    return router.createUrlTree(['/login']);
  }
};
