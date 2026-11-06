// Every row of the FR-5 import table, on one file.
import { A, B as C } from 'pkg-named';
import D from 'pkg-default';
import * as ns from 'pkg-namespace';
import 'pkg-side-effect';
import type { T } from 'pkg-types';
import { TestBed as TB } from '@angular/core/testing';
import { deep } from 'rxjs/internal/operators/deep';

// Own code: a relative path and a paths alias. Neither is a fact.
import { local } from './local';
import { shared } from '@app/shared';
import { widget } from '@demo/ui';

// Non-static specifiers are not resolved.
const notStatic = './x';
const dynamic = await import('pkg-dynamic');
const legacy = require('pkg-legacy');
const { a, b: renamed } = require('pkg-destructured');

export { Reexported } from 'pkg-reexport';
export * from 'pkg-star';

export const value = [
  A, C, D, T, TB, deep, local, shared, widget,
  ns, notStatic, dynamic, legacy, a, renamed,
];
