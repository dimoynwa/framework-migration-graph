import { Component } from '@angular/core';

@Component({
  selector: 'app-inline',
  standalone: true,
  template: `
    @if (ready) {
      <div *ngFor="let row of rows">{{ row.value | async }}</div>
    }
    @switch (mode) {
      @case ('a') {
        <span>{{ mode }}</span>
      }
    }
  `,
})
export class InlineComponent {
  ready = false;
  rows: unknown[] = [];
  mode = 'a';
}

@Component({
  selector: 'app-inline-escaped',
  template: '<p *ngIf="visible">{{ visible }}</p>',
})
export class EscapedComponent {
  visible = true;
}

@Component({
  selector: 'app-inline-string',
  template: '<p>literal in text, no binding</p>',
})
export class StringComponent {}
