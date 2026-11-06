import { TestBed } from '@angular/core/testing';
import { AppComponent } from './app.component';

describe('AppComponent', () => {
  beforeEach(() => TestBed.configureTestingModule({ imports: [AppComponent] }));

  it('creates the component', () => {
    expect(TestBed.createComponent(AppComponent)).toBeTruthy();
  });
});
