import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface AssessmentForm {
  projectName: string;
  application: string;
  operatingPressureBar: number | null;
  targetCycleRatePerMin: number | null;
  diagramAvailable: boolean;
  ioListAvailable: boolean;
  observedComponentsText: string;
  knownUnknownsText: string;
  currentQuoteHours: number | null;
  estimatedQuoteHours: number | null;
  engineeringHourlyCostInr: number | null;
}

interface AssessmentResponse {
  assessment_id: string;
  status: 'information_incomplete' | 'awaiting_engineer_review';
  requires_engineer_review: true;
  summary: string;
  missing_information: string[];
  known_unknowns: string[];
  review_checklist: string[];
  bom_status: 'not_generated';
  bom_note: string;
  roi_estimate: {
    engineering_hours_saved: number;
    estimated_cost_savings_inr: number;
  } | null;
}

@Component({
  imports: [FormsModule],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app-view.html',
})
export class App {
  protected form: AssessmentForm = this.emptyForm();
  protected readonly result = signal<AssessmentResponse | null>(null);
  protected readonly errorMessage = signal('');
  protected readonly submitting = signal(false);

  protected async runAssessment(): Promise<void> {
    this.submitting.set(true);
    this.errorMessage.set('');

    const payload = {
      project_name: this.form.projectName,
      application: this.form.application,
      operating_pressure_bar: this.form.operatingPressureBar,
      target_cycle_rate_per_min: this.form.targetCycleRatePerMin,
      diagram_available: this.form.diagramAvailable,
      io_list_available: this.form.ioListAvailable,
      observed_components: this.lines(this.form.observedComponentsText),
      known_unknowns: this.lines(this.form.knownUnknownsText),
      current_quote_hours: this.form.currentQuoteHours,
      estimated_quote_hours: this.form.estimatedQuoteHours,
      engineering_hourly_cost_inr: this.form.engineeringHourlyCostInr,
    };

    try {
      const response = await fetch('http://127.0.0.1:8000/assessments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = await response.json();

      if (!response.ok) {
        const detail = Array.isArray(body.detail)
          ? body.detail.map((item: { msg: string }) => item.msg).join(', ')
          : body.detail;
        throw new Error(detail || 'Assessment request failed.');
      }

      this.result.set(body as AssessmentResponse);
    } catch (error) {
      this.errorMessage.set(
        error instanceof Error
          ? `${error.message} Check that the backend is running on port 8000.`
          : 'Unable to reach the backend. Check that it is running on port 8000.',
      );
    } finally {
      this.submitting.set(false);
    }
  }

  protected loadSample(): void {
    this.form = {
      projectName: 'Demo packaging line',
      application: 'Case packer format-change retrofit',
      operatingPressureBar: 6,
      targetCycleRatePerMin: 30,
      diagramAvailable: true,
      ioListAvailable: true,
      observedComponentsText: 'V1 - valve manifold\nCY1 - guided actuator',
      knownUnknownsText: 'Confirm valve fail state from as-built machine',
      currentQuoteHours: 12,
      estimatedQuoteHours: 8,
      engineeringHourlyCostInr: 1200,
    };
    this.result.set(null);
    this.errorMessage.set('');
  }

  protected resetForm(): void {
    this.form = this.emptyForm();
    this.result.set(null);
    this.errorMessage.set('');
  }

  private emptyForm(): AssessmentForm {
    return {
      projectName: '',
      application: '',
      operatingPressureBar: null,
      targetCycleRatePerMin: null,
      diagramAvailable: false,
      ioListAvailable: false,
      observedComponentsText: '',
      knownUnknownsText: '',
      currentQuoteHours: null,
      estimatedQuoteHours: null,
      engineeringHourlyCostInr: null,
    };
  }

  private lines(value: string): string[] {
    return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  }
}
