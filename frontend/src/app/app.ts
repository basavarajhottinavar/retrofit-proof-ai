import { Component, ElementRef, OnDestroy, signal, ViewChild } from '@angular/core';
import { KeyValuePipe } from '@angular/common';
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
  legacyComponentNamesText: string;
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

interface ComponentNameMatch {
  project_id: string | null;
  source_file: string;
  source_sheet: string;
  source_row: number;
  drawing_item: number | null;
  legacy_part_number: string | null;
  description: string | null;
  competitor: string | null;
  festo_part_number: string | null;
  festo_type_code: string | null;
  source_remarks: string | null;
  reference_status: string;
  match_type: 'exact_part_number' | 'exact_component_name' | 'description_phrase';
  official_festo_product: OfficialFestoProduct | null;
  review_notice: string;
}

interface ComponentNameLookup {
  query: string;
  status: 'matched' | 'no_match' | 'not_available';
  matches_truncated: boolean;
  matches: ComponentNameMatch[];
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
  component_name_lookups: ComponentNameLookup[];
  source_documents: SourceDocumentSummary[];
  review_checklist: string[];
  bom_status: 'not_generated';
  bom_note: string;
  roi_estimate: {
    engineering_hours_saved: number;
    estimated_cost_savings_inr: number;
  } | null;
  bom_preview: BomPreviewItem[];
  validation_tests: ValidationTest[];
  ai_review: AiReview;
}

interface AiReview {
  enabled: boolean;
  provider: string;
  summary: string;
  risks: string[];
}

interface BomPreviewItem {
  legacy_part_number: string | null;
  description: string | null;
  festo_part_number: string | null;
  festo_type_code: string | null;
  quantity: number;
  review_status: string;
  disposition: 'engineer_review_required';
}

interface ValidationTest {
  phase: 'FAT' | 'SAT';
  test_id: string;
  title: string;
  acceptance_criteria: string;
  safety_note: string;
}

interface ProjectReconciliationRecord {
  source_row: number;
  drawing_item: number | null;
  legacy_part_number: string | null;
  description: string | null;
  competitor: string | null;
  festo_part_number: string | null;
  festo_type_code: string | null;
  source_sign: string | null;
  source_signoff_present: boolean;
  found_in_crt_source_value: string | null;
  source_remarks: string | null;
  review_caveats: string[];
  reference_status: string;
  requires_engineer_review: true;
  diagram_item_text: string | null;
  diagram_match_status: string;
  official_festo_product: OfficialFestoProduct | null;
}

interface OfficialFestoProduct {
  part_number: string;
  type_code: string;
  product_name: string;
  product_family: string;
  technical_data: Record<string, string>;
  product_page: string;
  datasheet: string;
  regional_availability: string;
  compatibility_status: string;
  dataset_source: string;
  retrieved_on: string;
  source_region: string;
}

interface LocalDiagramPreview {
  filename: string;
  kind: 'pdf' | 'image';
  objectUrl: string;
}

interface ProjectReconciliation {
  project_id: string | null;
  status: string;
  source_file: string;
  source_sheet?: string | null;
  source_signoff_present?: boolean;
  total_source_lines?: number;
  diagram_match_counts?: Record<string, number>;
  records: ProjectReconciliationRecord[];
  review_notice: string;
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
  project_reconciliation?: ProjectReconciliation | null;
}

@Component({
  imports: [FormsModule, KeyValuePipe],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app-view.html',
})
export class App implements OnDestroy {
  @ViewChild('documentInput') protected documentInput?: ElementRef<HTMLInputElement>;

  protected form: AssessmentForm = this.emptyForm();
  protected readonly result = signal<AssessmentResponse | null>(null);
  protected readonly errorMessage = signal('');
  protected readonly submitting = signal(false);
  protected readonly selectedFiles = signal<File[]>([]);
  protected readonly documentExtractions = signal<DocumentExtraction[]>([]);
  protected readonly localDiagramPreviews = signal<LocalDiagramPreview[]>([]);
  protected readonly extracting = signal(false);
  protected readonly engineerSignoff = signal<'review_required' | 'reviewed' | 'approved'>('review_required');
  protected readonly activeView = signal<'intake' | 'assessment'>('intake');

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
      legacy_component_names: this.lines(this.form.legacyComponentNamesText),
      source_documents: this.documentExtractions().map((document) => ({
        filename: document.filename,
        file_type: document.file_type,
        status: document.status,
        extracted_text: document.extracted_text,
        source_note: document.source_note,
        project_reconciliation: document.metadata['project_reconciliation'] as ProjectReconciliation | undefined,
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
      this.activeView.set('assessment');
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
    const files = Array.from(input.files ?? []);
    this.clearLocalDiagramPreviews();
    this.selectedFiles.set(files);
    this.localDiagramPreviews.set(
      files
        .flatMap((file): LocalDiagramPreview[] => {
          const extension = file.name.toLowerCase().split('.').pop();
          if (extension !== 'pdf' && !['png', 'jpg', 'jpeg'].includes(extension ?? '')) {
            return [];
          }
          const objectUrl = URL.createObjectURL(file);
          return [{
            filename: file.name,
            kind: extension === 'pdf' ? 'pdf' : 'image',
            objectUrl,
          }];
        })
        .slice(0, 4),
    );
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

  ngOnDestroy(): void {
    this.clearLocalDiagramPreviews();
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
        legacy_component_names: this.lines(this.form.legacyComponentNamesText),
        known_unknowns: this.lines(this.form.knownUnknownsText),
      },
      source_documents: assessment.source_documents,
      engineer_signoff: {
        status: this.engineerSignoff(),
        approved_by: '',
        approved_at: '',
      },
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

  protected async downloadReviewExcel(): Promise<void> {
    await this.downloadAssessmentExcel('crosswalk', 'retrofit-legacy-festo');
  }

  protected async downloadBomExcel(): Promise<void> {
    await this.downloadAssessmentExcel('bom', 'retrofit-candidate-bom');
  }

  protected async downloadValidationExcel(): Promise<void> {
    await this.downloadAssessmentExcel('validation_tests', 'retrofit-fat-sat-plan');
  }

  protected async downloadAssessmentExcel(exportType: string, defaultName: string): Promise<void> {
    const assessment = this.result();
    if (!assessment) return;

    try {
      const response = await fetch('http://localhost:8000/assessments/export-xlsx', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assessment, export_type: exportType }),
      });
      if (!response.ok) {
        throw new Error('Unable to generate the Excel crosswalk.');
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      const projectSlug = this.form.projectName.replace(/[^a-z0-9-_]+/gi, '-').replace(/^-|-$/g, '') || 'assessment';
      anchor.href = url;
      anchor.download = `${defaultName}-${projectSlug}.xlsx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      this.errorMessage.set(error instanceof Error ? error.message : 'Unable to download the Excel crosswalk.');
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
      legacyPartNumbersText: '',
      legacyComponentNamesText: '',
      knownUnknownsText: 'Confirm valve fail state from as-built machine',
      currentQuoteHours: 12,
      estimatedQuoteHours: 8,
      engineeringHourlyCostInr: 1200,
    };
    this.result.set(null);
    this.engineerSignoff.set('review_required');
    this.errorMessage.set('');
  }

  protected resetForm(): void {
    this.form = this.emptyForm();
    this.result.set(null);
    this.activeView.set('intake');
    this.engineerSignoff.set('review_required');
    this.errorMessage.set('');
    this.selectedFiles.set([]);
    this.documentExtractions.set([]);
    this.clearLocalDiagramPreviews();
    if (this.documentInput) this.documentInput.nativeElement.value = '';
  }

  private clearLocalDiagramPreviews(): void {
    for (const preview of this.localDiagramPreviews()) {
      URL.revokeObjectURL(preview.objectUrl);
    }
    this.localDiagramPreviews.set([]);
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
      legacyComponentNamesText: '',
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
