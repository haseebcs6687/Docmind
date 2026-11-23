# DocMind Evaluation Dataset: Ground Truth Facts

This document serves as the authoritative ground-truth answer key for evaluating RAG retrieval and response accuracy. All facts are derived from the fictional demo dataset for **Sterling & Rauf Law Associates** located in `data/sample_docs/`.

---

## 1. Ground Truth Knowledge Base Table

| Fact Description | Exact Value | Source File | Page / Section | Client-visible |
| :--- | :--- | :--- | :--- | :---: |
| Initial consultation fee & duration | PKR 5,000 for 45 minutes | `Fee_Schedule_2026.pdf` | Page 1, Section 1.1 | Y |
| Initial consultation fee waiver | Waived if client signs engagement within 7 days | `Fee_Schedule_2026.pdf` | Page 1, Section 1.2 | Y |
| Hourly rate: Senior Partner | PKR 25,000 per hour | `Fee_Schedule_2026.pdf` | Page 1, Section 2.1 (Table) | Y |
| Hourly rate: Associate Advocate | PKR 12,000 per hour | `Fee_Schedule_2026.pdf` | Page 1, Section 2.1 (Table) | Y |
| Hourly rate: Paralegal / Assistant | PKR 4,000 per hour | `Fee_Schedule_2026.pdf` | Page 1, Section 2.1 (Table) | Y |
| Retainer: Family Law matters | PKR 75,000 advance deposit | `Fee_Schedule_2026.pdf` | Page 2, Section 3.1 (Table) | Y |
| Retainer: Property & Real Estate | PKR 100,000 advance deposit | `Fee_Schedule_2026.pdf` | Page 2, Section 3.1 (Table) | Y |
| Retainer: Corporate Advisory | PKR 150,000 monthly retainer | `Fee_Schedule_2026.pdf` | Page 2, Section 3.1 (Table) | Y |
| Fixed fee: Contract Review | PKR 35,000 (up to 15 pages) | `Fee_Schedule_2026.pdf` | Page 2, Section 4.1 (Table) | Y |
| Fixed fee: Trademark Application | PKR 45,000 per class (excl. gov fees) | `Fee_Schedule_2026.pdf` | Page 2, Section 4.1 (Table) | Y |
| Fixed fee: Will & Succession Drafting | PKR 50,000 | `Fee_Schedule_2026.pdf` | Page 2, Section 4.1 (Table) | Y |
| Fixed fee: Legal Notice Issuance | PKR 20,000 | `Fee_Schedule_2026.pdf` | Page 2, Section 4.1 (Table) | Y |
| Fixed fee: Company Incorporation | PKR 60,000 | `Fee_Schedule_2026.pdf` | Page 2, Section 4.1 (Table) | Y |
| Invoice payment due date | Due within 15 days of issuance | `Fee_Schedule_2026.pdf` | Page 3, Section 5.2 | Y |
| Late payment surcharge | 2% per month on overdue balance | `Fee_Schedule_2026.pdf` | Page 3, Section 5.3 | Y |
| Retainer refund timeline | Within 30 days of case closure | `Fee_Schedule_2026.pdf` | Page 4, Section 8.2 | Y |
| Retainer refund administrative charge | 10% deducted from unused balance | `Fee_Schedule_2026.pdf` | Page 4, Section 8.3 | Y |
| Excluded practice areas (not handled) | Criminal defense and immigration matters | `Practice_Areas_Brochure.pdf` | Page 3, Section 5 | Y |
| Office hours: Weekdays (Mon-Fri) | 9:30 AM to 5:30 PM (9:30 - 17:30) | `Practice_Areas_Brochure.pdf` | Page 3, Section 6.3 | Y |
| Office hours: Saturday | 10:00 AM to 2:00 PM (10:00 - 14:00) | `Practice_Areas_Brochure.pdf` | Page 3, Section 6.3 | Y |
| Office closures | Sunday and gazetted public holidays | `Practice_Areas_Brochure.pdf` | Page 3, Section 6.3 | Y |
| Email inquiry response timeframe | Within 1 business day | `Practice_Areas_Brochure.pdf` | Page 3, Section 6.2 | Y |
| Conflict-of-interest check timeframe | 2 working days before engagement | `Practice_Areas_Brochure.pdf` | Page 3, Section 6.1 | Y |
| Conflict check validity period | 30 calendar days | `Client_Intake_SOP.pdf` | Page 2, Section 4.3 | N |
| Client file retention period | 7 years after case closure | `Confidentiality_and_Data_Policy.pdf` | Page 2, Section 4.1 | N |
| Internal data breach reporting window | Within 24 hours of discovery | `Confidentiality_and_Data_Policy.pdf` | Page 3, Section 5.2 | N |
| Client breach notification window | Within 72 hours (if risk of harm) | `Confidentiality_and_Data_Policy.pdf` | Page 3, Section 5.3 | N |
| Law firm official name | Sterling & Rauf Law Associates | `Practice_Areas_Brochure.pdf` | Page 1, Header | Y |
| Managing Partner name | Barrister Tariq Sterling | `Practice_Areas_Brochure.pdf` | Page 1, Section 2 (Table) | Y |
| Senior Partner name | Ayesha Rauf | `Practice_Areas_Brochure.pdf` | Page 1, Section 2 (Table) | Y |
| Senior Associate (Property) | Zainab Malik | `Practice_Areas_Brochure.pdf` | Page 1, Section 2 (Table) | Y |
| Associate (IP & Contracts) | Hamza Farooq | `Practice_Areas_Brochure.pdf` | Page 1, Section 2 (Table) | Y |
| Principal office location | Suite 402-404, Gulberg Executive Heights, Main Boulevard, Gulberg III, Lahore, Pakistan | `Practice_Areas_Brochure.pdf` | Page 3, Section 7 (Table) | Y |
| Official contact phone number | +92 42 3578 9000 | `Practice_Areas_Brochure.pdf` | Page 3, Section 7 (Table) | Y |
| Official intake email | contact@sterlingrauf.com | `Practice_Areas_Brochure.pdf` | Page 3, Section 7 (Table) | Y |
| Escalation email | escalation@sterlingrauf.com | `Client_Intake_SOP.pdf` | Page 4, Section 9.2 | N |
| Individual client KYC requirements | CNIC/Passport + utility bill within 90 days + 2 photos | `Client_Intake_SOP.pdf` | Page 3, Section 6.2 | N |
| Corporate client onboarding checklist | Certificate of Incorporation, Form A/29, Memorandum & Articles, Board Resolution | `Client_Intake_SOP.pdf` | Page 3, Section 6.3 | N |
| Approved payment methods | Direct Wire / IBFT to Allied Bank Limited; crossed Account Payee cheque | `Fee_Schedule_2026.pdf` | Page 3, Section 6.1 | Y |
| Cash transaction limit | Cash exceeding PKR 20,000 prohibited | `Fee_Schedule_2026.pdf` | Page 3, Section 6.2 | Y |
| Engagement termination notice | 14 calendar days written notice | `Client_Engagement_Letter_Template.docx` | Section 10.1 | Y |

---

## 2. Excluded Topics (Negative Test Cases / Out-of-Scope)

These topics are deliberately **omitted** from all documents in the knowledge base. When users query these topics, the RAG agent must clearly state that the information is **not present** in the provided documents and must **not hallucinate**:

1. **Parking**: Parking availability, reserved slots, visitor parking fees, or valet services at the Lahore office.
2. **Mobile Wallet Payments**: Online wallet services such as JazzCash, Easypaisa, SadaPay, or Nayapay digital wallets.
3. **Branch Offices**: Any presence or office branch in Karachi, Islamabad, Rawalpindi, or other cities (the firm operates solely from Lahore).
4. **Staff Salaries**: Associate salaries, partner earnings, paralegal compensation, or internal staff payroll amounts.
5. **Tax-Return Filing**: FBR income tax return preparation, personal tax filing, or annual wealth statement submission services.

---

## 3. Contract Key Terms (Staff-Only Ground Truth)

The following key terms represent the ground truth for contract analysis of sample commercial agreements in `data/sample_docs/`. Both contracts are restricted to staff visibility (`Client-visible = N`).

### 3.1. Master Services Agreement (`Master_Services_Agreement_Northgate.pdf`)

| Fact Description | Exact Value | Source File | Page / Section | Client-visible |
| :--- | :--- | :--- | :--- | :---: |
| Contract type | Master Services Agreement (IT Platform & Software Engineering) | `Master_Services_Agreement_Northgate.pdf` | Page 1, Header & Recitals | N |
| Parties | Northgate Logistics (Pvt) Ltd ("Client") and Brightline Software Solutions (Pvt) Ltd ("Service Provider") | `Master_Services_Agreement_Northgate.pdf` | Page 1, Section 1 | N |
| Effective date | 1 March 2026 | `Master_Services_Agreement_Northgate.pdf` | Page 1, Section 3.1 | N |
| Contract term | 24 months (commencing 1 March 2026 to 28 February 2028) | `Master_Services_Agreement_Northgate.pdf` | Page 1, Section 3.2 | N |
| Renewal mechanism | Auto-renews for successive 12-month terms unless 60 days' written notice | `Master_Services_Agreement_Northgate.pdf` | Page 1, Section 3.3 | N |
| Payment terms & fee | PKR 450,000 per month, invoiced monthly in advance, payable within 20 days | `Master_Services_Agreement_Northgate.pdf` | Page 2, Section 5.1, 5.2 | N |
| Late payment penalty | 1.5% per month on overdue balance | `Master_Services_Agreement_Northgate.pdf` | Page 2, Section 5.3 | N |
| Deliverables & IP ownership | Ownership of deliverables passes to Client upon full payment | `Master_Services_Agreement_Northgate.pdf` | Page 2, Section 7.1 | N |
| Confidentiality survival | Survives for 5 years after termination | `Master_Services_Agreement_Northgate.pdf` | Page 3, Section 8.2 | N |
| Limitation of liability | Capped at fees paid in preceding 12 months | `Master_Services_Agreement_Northgate.pdf` | Page 3, Section 9.1 | N |
| Termination for convenience | 90 days' written notice | `Master_Services_Agreement_Northgate.pdf` | Page 4, Section 11.1 | N |
| Termination for cause | 30-day cure period following written notification | `Master_Services_Agreement_Northgate.pdf` | Page 4, Section 11.2 | N |
| Governing law | Laws of Pakistan | `Master_Services_Agreement_Northgate.pdf` | Page 4, Section 12.1 | N |
| Dispute resolution | Arbitration in Lahore before a sole arbitrator | `Master_Services_Agreement_Northgate.pdf` | Page 4, Section 12.2 | N |
| Signatories | Mr. Bilal Ahmed (CEO, Northgate) and Ms. Sana Iqbal (Director, Brightline) | `Master_Services_Agreement_Northgate.pdf` | Page 4, Section 14 | N |
| Force majeure | NOT STATED (deliberately omitted) | `Master_Services_Agreement_Northgate.pdf` | N/A | N |

### 3.2. Commercial Lease Agreement (`Commercial_Lease_Agreement_Gulberg_Office.docx`)

| Fact Description | Exact Value | Source File | Page / Section | Client-visible |
| :--- | :--- | :--- | :--- | :---: |
| Contract type | Commercial Lease Agreement (Office Premises) | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Overview | N |
| Parties | Mr. Imran Qureshi ("Landlord") and Crescent Textiles (Pvt) Ltd ("Tenant") | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 1 | N |
| Commencement date | 1 April 2026 | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 3.1 | N |
| Lease term | 3 years (1 April 2026 to 31 March 2029) | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 3.2 | N |
| Renewal mechanism | NOT STATED (omitted from lease agreement) | `Commercial_Lease_Agreement_Gulberg_Office.docx` | N/A | N |
| Monthly rent & escalation | PKR 380,000 per month with 10% annual escalation at start of each year | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 4.1, 4.2 | N |
| Payment due date | On or before 5th of each month in advance | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 5.1 | N |
| Late payment fee | PKR 5,000 per day of delay | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 5.2 | N |
| Security deposit | 3 months' rent (PKR 1,140,000), refundable within 30 days of handover | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 6.1, 6.2 | N |
| Maintenance & repair obligations | Tenant: utilities & minor repairs; Landlord: structural repairs | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 7.1, 7.2, 7.3 | N |
| Termination notice | Either party on 60 days' written notice after initial 12-month lock-in | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 9.1, 9.2 | N |
| Governing law | Laws of Pakistan (including Punjab Rented Premises Act) | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 10.1 | N |
| Dispute resolution | Exclusive jurisdiction of courts of Lahore (no arbitration) | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 10.2 | N |
| Signatories | Mr. Imran Qureshi (Landlord) and Mr. Danish Rehman (MD, Crescent Textiles) | `Commercial_Lease_Agreement_Gulberg_Office.docx` | Section 12 | N |
| Force majeure | NOT STATED (deliberately omitted) | `Commercial_Lease_Agreement_Gulberg_Office.docx` | N/A | N |
| Liability cap | NOT STATED (deliberately omitted) | `Commercial_Lease_Agreement_Gulberg_Office.docx` | N/A | N |
| Indemnity clause | NOT STATED (deliberately omitted) | `Commercial_Lease_Agreement_Gulberg_Office.docx` | N/A | N |
| Confidentiality clause | NOT STATED (deliberately omitted) | `Commercial_Lease_Agreement_Gulberg_Office.docx` | N/A | N |

