import { TestBed } from '@angular/core/testing';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
    })
      .compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('should render the retrofit intake workspace', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('Retrofit intake');
    expect(compiled.querySelector('#project-name')).toBeTruthy();
    expect(compiled.querySelector('#legacy-component-names')).toBeTruthy();
    expect(compiled.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain('Project information & evidence');
  });

  it('should leave legacy identifiers blank when demo data is loaded', async () => {
    const fixture = TestBed.createComponent(App);
    const compiled = fixture.nativeElement as HTMLElement;
    await fixture.whenStable();
    fixture.detectChanges();
    const demoButton = Array.from(compiled.querySelectorAll('button'))
      .find((button) => button.textContent?.includes('Load demo data')) as HTMLButtonElement;

    demoButton.click();
    fixture.detectChanges();

    expect((compiled.querySelector('#legacy-parts') as HTMLTextAreaElement).value).toBe('');
    expect((compiled.querySelector('#legacy-component-names') as HTMLTextAreaElement).value).toBe('');
  });
});
