import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

export const authGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isLoggedIn()) {
    return router.createUrlTree(['/login']);
  }

  try {
    const me = auth.me() ?? (await auth.refreshMe());
    const needsLevel = !me.studyProfile.operationalLevel;
    if (needsLevel && !state.url.startsWith('/app/nivel')) {
      return router.createUrlTree(['/app/nivel']);
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
