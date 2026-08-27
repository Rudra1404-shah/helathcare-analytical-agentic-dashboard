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
