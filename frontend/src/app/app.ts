import { Component, ElementRef, signal, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface AssessmentForm {
  projectName: string;
  application: string;
  operatingPressureBar: number | null;
  targetCycleRatePerMin: number | null;
  diagramAvailable: boolean;
  ioListAvailable: boolean;
  observedComponentsText: string;
  legacyPartNumbersText: string;
  knownUnknownsText: string;
  currentQuoteHours: number | null;
  estimatedQuoteHours: number | null;
  engineeringHourlyCostInr: number | null;
}

interface ReferenceCandidate {
  part_number: string;
  product_type: string | null;
  note: string | null;
}

interface LocalReferenceRecord {
  source_file: string;
  source_sheet: string;
  source_row: number;
  legacy_part_number: string;
  legacy_description: string | null;
  family_or_function: string | null;
  technical_context: Record<string, string | null>;
  source_status: string | null;
  source_comment: string | null;
  candidates: ReferenceCandidate[];
  review_notice: string;
}

interface ReferenceLookup {
  query: string;
  found: boolean;
  records: LocalReferenceRecord[];
  review_notice: string;
}

interface AssessmentResponse {
  assessment_id: string;
  status: 'information_incomplete' | 'awaiting_engineer_review';
  requires_engineer_review: true;
  summary: string;
  missing_information: string[];
  known_unknowns: string[];
  reference_data_status: 'loaded' | 'partially_loaded' | 'not_available';
  reference_lookups: ReferenceLookup[];
  source_documents: SourceDocumentSummary[];
  review_checklist: string[];
  bom_status: 'not_generated';
  bom_note: string;
  roi_estimate: {
    engineering_hours_saved: number;
    estimated_cost_savings_inr: number;
  } | null;
}

interface DocumentExtraction {
  filename: string;
  file_type: string;
  status: 'text_extracted' | 'manual_review_required' | 'unsupported' | 'extraction_error';
  extracted_text: string;
  source_note: string;
  metadata: Record<string, unknown>;
}

interface SourceDocumentSummary {
  filename: string;
  file_type: string;
  status: DocumentExtraction['status'];
  source_note: string;
}

@Component({
  imports: [FormsModule],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app-view.html',
})
export class App {
  @ViewChild('documentInput') protected documentInput?: ElementRef<HTMLInputElement>;

  protected form: AssessmentForm = this.emptyForm();
  protected readonly result = signal<AssessmentResponse | null>(null);
  protected readonly errorMessage = signal('');
  protected readonly submitting = signal(false);
  protected readonly selectedFiles = signal<File[]>([]);
  protected readonly documentExtractions = signal<DocumentExtraction[]>([]);
  protected readonly extracting = signal(false);

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
      legacy_part_numbers: this.lines(this.form.legacyPartNumbersText),
      source_documents: this.documentExtractions().map((document) => ({
        filename: document.filename,
        file_type: document.file_type,
        status: document.status,
        extracted_text: document.extracted_text,
        source_note: document.source_note,
      })),
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

  protected onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFiles.set(Array.from(input.files ?? []));
    this.documentExtractions.set([]);
    this.errorMessage.set('');
  }

  protected async extractDocuments(): Promise<void> {
    if (!this.selectedFiles().length) {
      this.errorMessage.set('Select at least one source document.');
      return;
    }

    this.extracting.set(true);
    this.errorMessage.set('');
    const formData = new FormData();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    for (const file of this.selectedFiles()) {
      formData.append('files', file, file.name);
    }

    try {
      const response = await fetch('http://127.0.0.1:8000/documents/extract', {
        method: 'POST',
        body: formData,
        signal: controller.signal,
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.detail || 'Document extraction failed.');
      }
      this.documentExtractions.set(body.documents as DocumentExtraction[]);
    } catch (error) {
      this.errorMessage.set(
        error instanceof DOMException && error.name === 'AbortError'
          ? 'Local extraction timed out. Try fewer or smaller documents.'
          : error instanceof Error
          ? `${error.message} Check that the backend is running on port 8000.`
          : 'Unable to reach the local document service.',
      );
    } finally {
      clearTimeout(timeoutId);
      this.extracting.set(false);
    }
  }

  protected updateExtractedText(index: number, event: Event): void {
    const extractedText = (event.target as HTMLTextAreaElement).value;
    this.documentExtractions.update((documents) =>
      documents.map((item, itemIndex) =>
        itemIndex === index ? { ...item, extracted_text: extractedText } : item,
      ),
    );
  }

  protected statusLabel(status: string): string {
    return status.replaceAll('_', ' ');
  }

  protected downloadReviewPacket(): void {
    const assessment = this.result();
    if (!assessment) return;

    const packet = {
      title: 'RetrofitProof AI engineer review packet',
      generated_at: new Date().toISOString(),
      disclaimer: 'Review aid only. Not a design approval, sizing result, executable test procedure, or approved BOM.',
      intake: {
        project_name: this.form.projectName,
        application: this.form.application,
        operating_pressure_bar: this.form.operatingPressureBar,
        target_cycle_rate_per_min: this.form.targetCycleRatePerMin,
        diagram_available_and_reviewed: this.form.diagramAvailable,
        io_list_available_and_reviewed: this.form.ioListAvailable,
        observed_components: this.lines(this.form.observedComponentsText),
        legacy_part_numbers: this.lines(this.form.legacyPartNumbersText),
        known_unknowns: this.lines(this.form.knownUnknownsText),
      },
      source_documents: assessment.source_documents,
      assessment,
    };
    const blob = new Blob([JSON.stringify(packet, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    const projectSlug = this.form.projectName.replace(/[^a-z0-9-_]+/gi, '-').replace(/^-|-$/g, '') || 'assessment';
    anchor.href = url;
    anchor.download = `retrofit-review-${projectSlug}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
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
      legacyPartNumbersText: '',
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
    this.selectedFiles.set([]);
    this.documentExtractions.set([]);
    if (this.documentInput) this.documentInput.nativeElement.value = '';
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
      legacyPartNumbersText: '',
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
