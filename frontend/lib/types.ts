/**
 * Types mirroring the platform's Pydantic schemas.
 *
 * Money is `string`, never `number`. The backend stores Decimal precisely so a
 * rounding drift cannot become an Overcharging complaint; parsing it into a
 * JavaScript float here would undo that. Format it, never compute with it.
 */

export type UserRole =
  | "GOVT_ADMIN"
  | "HOSPITAL_ADMIN"
  | "HOSPITAL_STAFF"
  | "DOCTOR"
  | "CITIZEN";

export type SectorType = "PUBLIC" | "PRIVATE" | "TRUST";

export type AccreditationStatus =
  | "NABH"
  | "STATE_LICENSED"
  | "PENDING"
  | "BLACKLISTED";

export type CaseStatus =
  | "ADMITTED"
  | "ICU"
  | "OBSERVATION"
  | "DISCHARGED"
  | "DECEASED";

export type TriageLevel = 1 | 2 | 3 | 4;

export type ShiftType = "MORNING" | "EVENING" | "NIGHT" | "GENERAL";

export type StaffCategory = "ADMIN_SUPPORT" | "MEDICAL";

export type StaffStatus =
  | "ACTIVE"
  | "INACTIVE"
  | "ON_LEAVE"
  | "SUSPENDED"
  | "TERMINATED";

export type InventoryCategory =
  | "GENERAL_BEDS"
  | "ICU_BEDS"
  | "VENTILATORS"
  | "OXYGEN_CYLINDERS"
  | "OXYGEN_LITERS"
  | "MEDICINES"
  | "CONSUMABLES";

export type PaymentStatus =
  | "PENDING"
  | "PARTIALLY_PAID"
  | "PAID"
  | "CANCELLED"
  | "REFUNDED";

export type ComplaintCategory =
  | "OVERCHARGING"
  | "BED_REFUSAL"
  | "NEGLIGENCE"
  | "HYGIENE"
  | "SHORTAGE"
  | "FALSE_BILLING";

export type InvestigationStatus =
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "INQUIRY_ASSIGNED"
  | "ACTION_TAKEN"
  | "DISMISSED";

export type ActionTaken = "WARNING" | "FINE" | "LICENSE_SUSPENSION" | "DISMISSED";

export type EvidenceType = "PHOTO" | "VIDEO";

export type Gender = "MALE" | "FEMALE" | "OTHER" | "UNDISCLOSED";

/**
 * Clinical staff carry a registration number and can be put on call; admin and
 * support staff cannot. The split decides which intake endpoint a role posts
 * to, so the two lists are kept apart rather than filtered out of one.
 */
export type MedicalStaffRole =
  | "STAFF_NURSE"
  | "MATRON"
  | "LAB_ASSISTANT"
  | "WARD_BOY"
  | "COMPOUNDER";

export type AdminSupportStaffRole =
  | "DESK_ADMIN"
  | "ADMIN"
  | "ACCOUNTANT"
  | "CLEANER"
  | "SECURITY"
  | "DRIVER"
  | "LIFTMAN"
  | "HELPER";

export type StaffRole = MedicalStaffRole | AdminSupportStaffRole;

export type EmploymentType = "FULL_TIME" | "VISITING" | "ON_CALL";

export type DiseaseCategory =
  | "INFECTIOUS"
  | "CHRONIC"
  | "TRAUMA"
  | "SURGICAL"
  | "PEDIATRIC"
  | "MATERNAL";

export type InventoryUnit =
  | "UNITS"
  | "LITERS"
  | "PIECES"
  | "BOXES"
  | "VIALS"
  | "STRIPS"
  | "KG"
  | "ML";

export type PaymentMode =
  | "CASH"
  | "CARD"
  | "UPI"
  | "NET_BANKING"
  | "INSURANCE"
  | "GOVT_SCHEME";

// --------------------------------------------------------------------------
// Envelope
// --------------------------------------------------------------------------
export interface PageMeta {
  total: number;
  page: number;
  limit: number;
}

export interface Paginated<T> {
  items: T[];
  meta: PageMeta;
}

export interface ApiEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta: PageMeta | null;
}

interface Identified {
  _id: string;
  created_at: string;
  updated_at: string;
}

// --------------------------------------------------------------------------
// Resources
// --------------------------------------------------------------------------
export interface SessionUser extends Identified {
  email: string;
  role: UserRole;
  full_name: string;
  phone: string | null;
  hospital_id: string | null;
  is_active: boolean;
  is_verified: boolean;
  last_login_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
  role: UserRole;
}

export interface Zone extends Identified {
  zone_code: string;
  name: string;
  state: string;
  city: string;
  population_covered: number;
  is_active: boolean;
}

export interface HospitalCapacity {
  total_sanctioned_beds: number;
  icu_beds: number;
  emergency_beds: number;
  ventilators: number;
  oxygen_bulk_capacity_liters: number;
  ambulance_count: number;
}

export interface Hospital extends Identified {
  name: string;
  license_no: string;
  sector_type: SectorType;
  state: string;
  city: string;
  zone_code: string;
  ward_area: string | null;
  capacity: HospitalCapacity;
  accreditation_status: AccreditationStatus;
  accredited_on: string | null;
  license_valid_until: string | null;
  nodal_officer_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  is_active: boolean;
}

export interface Department extends Identified {
  hospital_id: string;
  name: string;
  code: string;
  floor: string | null;
  wing: string | null;
  hod_doctor_id: string | null;
  bed_count: number;
  is_active: boolean;
}

export interface Staff extends Identified {
  hospital_id: string;
  employee_id: string;
  full_name: string;
  phone: string;
  staff_category: StaffCategory;
  role: string;
  registration_no: string | null;
  department_id: string | null;
  assigned_ward_area: string | null;
  shift: ShiftType;
  is_emergency_on_call: boolean;
  status: StaffStatus;
}

export interface Doctor extends Identified {
  hospital_id: string;
  full_name: string;
  license_no: string;
  specialization: string;
  department_id: string;
  qualification: string;
  phone: string | null;
  email: string | null;
  employment_type: string;
  shifts: ShiftType[];
  max_daily_patients: number;
  is_emergency_on_call: boolean;
  status: StaffStatus;
}

export interface Patient extends Identified {
  hospital_id: string;
  mrn: string;
  citizen_user_id: string | null;
  full_name: string;
  gender: Gender;
  date_of_birth: string | null;
  age_years: number | null;
  phone: string | null;
  blood_group: string;
  allergies: string[];
  pre_existing_conditions: string[];
  is_active: boolean;
}

export interface VitalSigns {
  systolic_bp: number;
  diastolic_bp: number;
  pulse_bpm: number;
  spo2_percent: number;
  temperature_celsius: number;
  respiratory_rate: number | null;
  recorded_at: string;
}

export interface Prescription {
  medicine_name: string;
  dosage: string;
  frequency: string;
  duration_days: number;
  notes: string | null;
  prescribed_at: string;
}

export interface PatientCase extends Identified {
  case_number: string;
  hospital_id: string;
  patient_id: string;
  doctor_id: string;
  department_id: string;
  case_type_id: string | null;
  bed_allocated: string | null;
  triage_level: TriageLevel | null;
  admitted_at: string;
  discharged_at: string | null;
  chief_symptoms: string[];
  vitals: VitalSigns[];
  prescriptions: Prescription[];
  status: CaseStatus;
  discharge_summary: string | null;
}

export interface CaseType extends Identified {
  hospital_id: string | null;
  name: string;
  disease_category: string;
  icd10_code: string;
  triage_level: TriageLevel;
  description: string | null;
  is_notifiable: boolean;
  is_active: boolean;
}

export interface InventoryItem extends Identified {
  hospital_id: string;
  category: InventoryCategory;
  item_name: string;
  total_stock: number;
  available_stock: number;
  min_safety_threshold: number;
  unit: string;
  last_restocked_at: string | null;
  expires_on: string | null;
  is_active: boolean;
}

export interface CapacityCard {
  category: InventoryCategory;
  total_stock: number;
  available_stock: number;
  in_use: number;
  min_safety_threshold: number;
  unit: string | null;
  utilisation_ratio: number;
  is_below_threshold: boolean;
  line_count: number;
}

export interface LowStockAlert {
  hospital_id: string;
  item_id: string;
  category: InventoryCategory;
  item_name: string;
  available_stock: number;
  min_safety_threshold: number;
  unit: string;
}

export interface BillLineItem {
  description: string;
  rate: string;
  quantity: string;
  total: string;
}

export interface Bill extends Identified {
  invoice_no: string;
  hospital_id: string;
  case_id: string;
  patient_id: string;
  line_items: BillLineItem[];
  subtotal: string;
  tax_amount: string;
  discount_amount: string;
  grand_total: string;
  amount_paid: string;
  payment_status: PaymentStatus;
  payment_mode: string | null;
  issued_at: string;
  settled_at: string | null;
}

export interface EvidenceAttachment {
  url: string;
  evidence_type: EvidenceType;
  content_type: string;
  file_name: string | null;
  size_bytes: number;
  checksum_sha256: string | null;
  uploaded_at: string;
}

export interface Complaint extends Identified {
  complaint_number: string;
  citizen_user_id: string;
  hospital_id: string;
  department_id: string | null;
  incident_at: string;
  category: ComplaintCategory;
  description: string;
  evidence: EvidenceAttachment[];
  investigation_status: InvestigationStatus;
  assigned_officer_id: string | null;
  hospital_explanation: string | null;
  action_taken: ActionTaken | null;
  closure_remarks: string | null;
  closed_at: string | null;
}

export interface UploadedFile {
  url: string;
  file_name: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
}

export interface BulkUploadRowError {
  row_number: number;
  field: string | null;
  message: string;
}

export interface BulkUploadReport {
  total_rows: number;
  accepted: number;
  rejected: number;
  errors: BulkUploadRowError[];
}

export interface PhrHospitalSummary {
  hospital_id: string;
  name: string;
  city: string;
  state: string;
}

export interface PhrBillSummary {
  invoice_no: string;
  grand_total: string;
  amount_paid: string;
  payment_status: PaymentStatus;
  issued_at: string;
}

export interface PhrCaseEntry {
  case_id: string;
  case_number: string;
  hospital: PhrHospitalSummary;
  department_name: string | null;
  doctor_name: string | null;
  case_type_name: string | null;
  admitted_at: string;
  discharged_at: string | null;
  status: CaseStatus;
  chief_symptoms: string[];
  vitals: VitalSigns[];
  prescriptions: Prescription[];
  discharge_summary: string | null;
  bill: PhrBillSummary | null;
}

export interface HealthRecord {
  citizen_user_id: string;
  full_name: string;
  gender: Gender;
  date_of_birth: string | null;
  age_years: number | null;
  blood_group: string;
  allergies: string[];
  pre_existing_conditions: string[];
  linked_patient_ids: string[];
  cases: PhrCaseEntry[];
  generated_at: string;
}

// ---------------------------------------------------------------------------
// Analytical intelligence (Phase 4)
//
// Mirrors src/domain/schemas/analytics.py. Ratios and rates are `number | null`
// rather than defaulting to zero, because the backend distinguishes "undefined
// here" from "genuinely zero" and a view that collapses the two would show an
// empty ICU where there is in fact no ICU.
// ---------------------------------------------------------------------------

export type AlertTier = "CRITICAL" | "HIGH" | "MEDIUM" | "INFO";

export type AlertKind =
  | "BED_CAPACITY"
  | "ICU_CAPACITY"
  | "STOCK_DEPLETION"
  | "OUTBREAK_ANOMALY"
  | "WORKFORCE_OVERLOAD"
  | "SURGE_FORECAST";

export type TrendDirection = "RISING" | "FALLING" | "STABLE";

export type SignalConfidence = "HIGH" | "MODERATE" | "LOW" | "INSUFFICIENT_DATA";

export type EstimationBasis = "ESTIMATED_FROM_CASE_DEMAND" | "INSUFFICIENT_HISTORY";

export interface TriageBreakdownEntry {
  triage_level: TriageLevel;
  open_cases: number;
}

export interface RealtimeMonitoring {
  hospital_id: string | null;
  hospital_count: number;
  open_cases: number;
  admitted_cases: number;
  icu_cases: number;
  observation_cases: number;
  total_sanctioned_beds: number;
  icu_beds: number;
  bed_occupancy_ratio: number | null;
  icu_occupancy_ratio: number | null;
  ventilator_utilisation_ratio: number | null;
  oxygen_utilisation_ratio: number | null;
  triage_breakdown: TriageBreakdownEntry[];
  unclassified_cases: number;
  generated_at: string;
}

export interface OutbreakSignal {
  zone_code: string;
  zone_name: string;
  state: string;
  city: string;
  case_type_id: string | null;
  case_type_name: string;
  icd10_code: string;
  population_covered: number;
  observed_cases: number;
  observed_rate_per_100k: number | null;
  baseline_mean_rate_per_100k: number | null;
  z_score: number | null;
  is_anomaly: boolean;
  confidence: SignalConfidence;
  baseline_days: number;
}

export interface OutbreakDetection {
  signals: OutbreakSignal[];
  anomaly_count: number;
  evaluated_count: number;
  window_days: number;
  threshold: number;
  generated_at: string;
}

export interface ForecastPoint {
  horizon_day: number;
  forecast_date: string;
  predicted_admissions: number;
  lower_bound: number;
  upper_bound: number;
}

export interface SurgeForecast {
  hospital_id: string | null;
  history: number[];
  history_window_days: number;
  observations: number;
  points: ForecastPoint[];
  horizon_days: number;
  trend_direction: TrendDirection;
  trend_per_day: number;
  confidence: SignalConfidence;
  projected_7_day_total: number;
  projected_14_day_total: number;
  generated_at: string;
}

export interface DoctorLoad {
  doctor_id: string;
  full_name: string;
  specialization: string;
  department_id: string;
  is_available: boolean;
  active_load: number;
  max_daily_patients: number;
  burnout_index: number | null;
  is_overloaded: boolean;
}

export interface DepartmentLoad {
  department_id: string;
  doctor_count: number;
  active_load: number;
  daily_capacity: number;
  burnout_index: number | null;
}

export interface ShiftBalance {
  shift: ShiftType;
  doctor_count: number;
  medical_staff_count: number;
  support_staff_count: number;
}

export interface ReallocationSuggestion {
  from_department_id: string;
  to_department_id: string;
  from_burnout_index: number;
  to_burnout_index: number;
  reason: string;
}

export interface WorkforceReallocation {
  hospital_id: string | null;
  has_capacity_data: boolean;
  doctor_count: number;
  active_doctor_count: number;
  total_active_load: number;
  total_daily_capacity: number;
  mean_burnout_index: number | null;
  overloaded_doctor_count: number;
  doctors: DoctorLoad[];
  departments: DepartmentLoad[];
  shift_balance: ShiftBalance[];
  suggestions: ReallocationSuggestion[];
  generated_at: string;
}

export interface ResourceProjection {
  hospital_id: string;
  category: InventoryCategory;
  line_count: number;
  total_stock: number;
  available_stock: number;
  min_safety_threshold: number;
  unit: InventoryUnit | null;
  daily_burn_rate: number;
  days_to_stockout: number | null;
  projected_stockout_on: string | null;
  is_below_threshold: boolean;
  basis: EstimationBasis;
  window_days: number;
}

export interface ResourcePrediction {
  projections: ResourceProjection[];
  at_risk_count: number;
  window_days: number;
  basis: EstimationBasis;
  generated_at: string;
}

export interface SmartAlert {
  tier: AlertTier;
  kind: AlertKind;
  hospital_id: string | null;
  title: string;
  detail: string;
  metric_value: number | null;
  threshold_value: number | null;
  recommended_action: string;
}

export interface SmartAlerts {
  alerts: SmartAlert[];
  critical_count: number;
  high_count: number;
  medium_count: number;
  info_count: number;
  generated_at: string;
}

export interface CategoryCount {
  category: ComplaintCategory;
  count: number;
}

export interface StatusCount {
  status: InvestigationStatus;
  count: number;
}

export interface ActionCount {
  action: ActionTaken;
  count: number;
}

export interface RecidivismEntry {
  hospital_id: string;
  category: ComplaintCategory;
  action_taken: ActionTaken;
  complaints_before_action: number;
  complaints_after_action: number;
}

export interface PolicyImpact {
  hospital_id: string | null;
  total_complaints: number;
  closed_complaints: number;
  open_complaints: number;
  by_category: CategoryCount[];
  by_status: StatusCount[];
  by_action: ActionCount[];
  mean_resolution_days: number | null;
  median_resolution_days: number | null;
  enforcement_rate: number | null;
  repeat_offender_count: number;
  recidivism: RecidivismEntry[];
  generated_at: string;
}

export interface NationalOverview {
  hospital_count: number;
  zone_count: number;
  population_covered: number;
  open_cases: number;
  total_sanctioned_beds: number;
  bed_occupancy_ratio: number | null;
  icu_occupancy_ratio: number | null;
  critical_alert_count: number;
  high_alert_count: number;
  outbreak_signal_count: number;
  at_risk_resource_count: number;
  open_complaint_count: number;
  generated_at: string;
}
