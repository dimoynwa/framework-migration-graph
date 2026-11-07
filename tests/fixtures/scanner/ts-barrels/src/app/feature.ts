// AC-2 / AC-2.2 / AC-2.3 at the import site: ``npm:@angular/core#inject`` is
// recorded at line 2 (this file), not in any barrel.
import {
  inject,
  di,
  effect,
  LiveAnnouncer,
  utilFn,
} from '@app/core';

inject(TOKEN);
di.call(TOKEN);
effect(onChanged);
LiveAnnouncer.announce('saved');
utilFn();
