// AC-2.2: a namespace import of a barrel resolves per member
// (``core.inject`` → ``npm:@angular/core#inject``), and a namespaced decorator
// keeps its symbol (``@core.Component({…})`` → ``npm:@angular/core#Component``).
import * as core from '@app/core';

core.inject(TOKEN);
core.effect(onChanged);
core.unknownSymbol();

@core.Component({ selector: 'x', standalone: true })
export class Namespaced {}
