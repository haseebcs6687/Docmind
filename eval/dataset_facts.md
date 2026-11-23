# DocMind Evaluation Dataset: Ground Truth Facts

This document serves as the authoritative ground-truth answer key for evaluating RAG retrieval and response accuracy. All facts are derived from the fictional demo dataset for **Sterling & Rauf Law Associates** located in `data/sample_docs/`.

---

## 1. Ground Truth Knowledge Base Table

| Fact Description | Exact Value | Source File | Page / Section |
| :--- | :--- | :--- | :--- |
| Initial consultation fee & duration | PKR 5,000 for 45 minutes | `Fee_Schedule_2026.pdf` | Page 1, Section 1.1 |
| Initial consultation fee waiver | Waived if client signs engagement within 7 days | `Fee_Schedule_2026.pdf` | Page 1, Section 1.2 |
| Hourly rate: Senior Partner | PKR 25,000 per hour | `Fee_Schedule_2026.pdf` | Page 1, Section 2.1 (Table) |
| Hourly rate: Associate Advocate | PKR 12,000 per hour | `Fee_Schedule_2026.pdf` | Page 1, Section 2.1 (Table) |
| Hourly rate: Paralegal / Assistant | PKR 4,000 per hour | `Fee_Schedule_2026.pdf` | Page 1, Section 2.1 (Table) |
| Retainer: Family Law matters | PKR 75,000 advance deposit | `Fee_Schedule_2026.pdf` | Page 2, Section 3.1 (Table) |
| Retainer: Property & Real Estate | PKR 100,000 advance deposit | `Fee_Schedule_2026.pdf` | Page 2, Section 3.1 (Table) |
| Retainer: Corporate Advisory | PKR 150,000 monthly retainer | `Fee_Schedule_2026.pdf` | Page 2, Section 3.1 (Table) |
| Fixed fee: Contract Review | PKR 35,000 (up to 15 pages) | `Fee_Schedule_2026.pdf` | Page 2, Section 4.1 (Table) |
| Fixed fee: Trademark Application | PKR 45,000 per class (excl. gov fees) | `Fee_Schedule_2026.pdf` | Page 2, Section 4.1 (Table) |
| Fixed fee: Will & Succession Drafting | PKR 50,000 | `Fee_Schedule_2026.pdf` | Page 2, Section 4.1 (Table) |
| Fixed fee: Legal Notice Issuance | PKR 20,000 | `Fee_Schedule_2026.pdf` | Page 2, Section 4.1 (Table) |
| Fixed fee: Company Incorporation | PKR 60,000 | `Fee_Schedule_2026.pdf` | Page 2, Section 4.1 (Table) |
| Invoice payment due date | Due within 15 days of issuance | `Fee_Schedule_2026.pdf` | Page 3, Section 5.2 |
| Late payment surcharge | 2% per month on overdue balance | `Fee_Schedule_2026.pdf` | Page 3, Section 5.3 |
| Retainer refund timeline | Within 30 days of case closure | `Fee_Schedule_2026.pdf` | Page 4, Section 8.2 |
| Retainer refund administrative charge | 10% deducted from unused balance | `Fee_Schedule_2026.pdf` | Page 4, Section 8.3 |
| Excluded practice areas (not handled) | Criminal defense and immigration matters | `Practice_Areas_Brochure.pdf` | Page 3, Section 5 |
| Office hours: Weekdays (Mon-Fri) | 9:30 AM to 5:30 PM (9:30 - 17:30) | `Practice_Areas_Brochure.pdf` | Page 3, Section 6.3 |
| Office hours: Saturday | 10:00 AM to 2:00 PM (10:00 - 14:00) | `Practice_Areas_Brochure.pdf` | Page 3, Section 6.3 |
| Office closures | Sunday and gazetted public holidays | `Practice_Areas_Brochure.pdf` | Page 3, Section 6.3 |
| Email inquiry response timeframe | Within 1 business day | `Practice_Areas_Brochure.pdf` | Page 3, Section 6.2 |
| Conflict-of-interest check timeframe | 2 working days before engagement | `Practice_Areas_Brochure.pdf` | Page 3, Section 6.1 |
| Conflict check validity period | 30 calendar days | `Client_Intake_SOP.pdf` | Page 2, Section 4.3 |
| Client file retention period | 7 years after case closure | `Confidentiality_and_Data_Policy.pdf` | Page 2, Section 4.1 |
| Internal data breach reporting window | Within 24 hours of discovery | `Confidentiality_and_Data_Policy.pdf` | Page 3, Section 5.2 |
| Client breach notification window | Within 72 hours (if risk of harm) | `Confidentiality_and_Data_Policy.pdf` | Page 3, Section 5.3 |
| Law firm official name | Sterling & Rauf Law Associates | `Practice_Areas_Brochure.pdf` | Page 1, Header |
| Managing Partner name | Barrister Tariq Sterling | `Practice_Areas_Brochure.pdf` | Page 1, Section 2 (Table) |
| Senior Partner name | Ayesha Rauf | `Practice_Areas_Brochure.pdf` | Page 1, Section 2 (Table) |
| Senior Associate (Property) | Zainab Malik | `Practice_Areas_Brochure.pdf` | Page 1, Section 2 (Table) |
| Associate (IP & Contracts) | Hamza Farooq | `Practice_Areas_Brochure.pdf` | Page 1, Section 2 (Table) |
| Principal office location | Suite 402-404, Gulberg Executive Heights, Main Boulevard, Gulberg III, Lahore, Pakistan | `Practice_Areas_Brochure.pdf` | Page 3, Section 7 (Table) |
| Official contact phone number | +92 42 3578 9000 | `Practice_Areas_Brochure.pdf` | Page 3, Section 7 (Table) |
| Official intake email | contact@sterlingrauf.com | `Practice_Areas_Brochure.pdf` | Page 3, Section 7 (Table) |
| Escalation email | escalation@sterlingrauf.com | `Client_Intake_SOP.pdf` | Page 4, Section 9.2 |
| Individual client KYC requirements | CNIC/Passport + utility bill within 90 days + 2 photos | `Client_Intake_SOP.pdf` | Page 3, Section 6.2 |
| Corporate client onboarding checklist | Certificate of Incorporation, Form A/29, Memorandum & Articles, Board Resolution | `Client_Intake_SOP.pdf` | Page 3, Section 6.3 |
| Approved payment methods | Direct Wire / IBFT to Allied Bank Limited; crossed Account Payee cheque | `Fee_Schedule_2026.pdf` | Page 3, Section 6.1 |
| Cash transaction limit | Cash exceeding PKR 20,000 prohibited | `Fee_Schedule_2026.pdf` | Page 3, Section 6.2 |
| Engagement termination notice | 14 calendar days written notice | `Client_Engagement_Letter_Template.docx` | Section 10.1 |

---

## 2. Excluded Topics (Negative Test Cases / Out-of-Scope)

These topics are deliberately **omitted** from all documents in the knowledge base. When users query these topics, the RAG agent must clearly state that the information is **not present** in the provided documents and must **not hallucinate**:

1. **Parking**: Parking availability, reserved slots, visitor parking fees, or valet services at the Lahore office.
2. **Mobile Wallet Payments**: Online wallet services such as JazzCash, Easypaisa, SadaPay, or Nayapay digital wallets.
3. **Branch Offices**: Any presence or office branch in Karachi, Islamabad, Rawalpindi, or other cities (the firm operates solely from Lahore).
4. **Staff Salaries**: Associate salaries, partner earnings, paralegal compensation, or internal staff payroll amounts.
5. **Tax-Return Filing**: FBR income tax return preparation, personal tax filing, or annual wealth statement submission services.
