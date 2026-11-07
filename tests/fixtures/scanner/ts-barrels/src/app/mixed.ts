// AC-2.3: a name that ends in a local declaration is own code and is not
// recorded; a name that reaches a package is.
import { LocalHelper, helper, inject } from '@app/mixed-barrel';

helper();
inject(TOKEN);
LocalHelper.q();
