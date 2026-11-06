// A workspace package's own barrel: an import of ``@demo/ui`` from the app
// reaches these through the package entry point in its ``package.json``.
export { Button } from './button';
export { announce } from '@angular/cdk/a11y';
