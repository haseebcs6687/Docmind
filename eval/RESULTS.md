# DocMind Evaluation Benchmark: Results & Analysis

**Date**: 2026-11-24 13:48:23 UTC  
**Dataset**: 8 Documents, 97 Chunks (`data/sample_docs/`)  
**Benchmark Size**: 38 Questions across 6 Distinct Categories  
**Overall Accuracy**: **100.0%** (38/38)  
**Runtime Duration**: 517.6s  

---

## 1. Headline Accuracy by Category

| Category | Questions | Passed | Failed | Errors | Pass Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`fact_client`** | 12 | 12 | 0 | 0 | **100.0%** |
| **`fact_staff`** | 6 | 6 | 0 | 0 | **100.0%** |
| **`access_control`** | 6 | 6 | 0 | 0 | **100.0%** |
| **`not_in_docs`** | 7 | 7 | 0 | 0 | **100.0%** |
| **`multi_turn`** | 3 | 3 | 0 | 0 | **100.0%** |
| **`adversarial`** | 4 | 4 | 0 | 0 | **100.0%** |
| **OVERALL TOTAL** | **38** | **38** | **0** | **0** | **100.0%** |

---

## 2. Retrieval Score Threshold Sensitivity Sweep (0.55 – 0.75)

The table below analyzes overall benchmark accuracy across score thresholds from 0.55 to 0.75 in 0.01 increments. Simulated offline from the retrieved scores of the evaluation benchmark run:

| Threshold | Simulated Pass Rate | Total Passed | Total Failed | Retrieval Gated Questions |
| :---: | :---: | :---: | :---: | :---: |
| **0.55** | **55.3%** | 21/38 | 17/38 | 0 |
| **0.56** | **57.9%** | 22/38 | 16/38 | 0 |
| **0.57** | **60.5%** | 23/38 | 15/38 | 0 |
| **0.58** | **60.5%** | 23/38 | 15/38 | 0 |
| **0.59** | **60.5%** | 23/38 | 15/38 | 0 |
| **0.60** | **63.2%** | 24/38 | 14/38 | 0 |
| **0.61** | **68.4%** | 26/38 | 12/38 | 0 |
| **0.62** | **68.4%** | 26/38 | 12/38 | 0 |
| **0.63** | **73.7%** | 28/38 | 10/38 | 0 |
| **0.64** | **78.9%** | 30/38 | 8/38 | 0 |
| **0.65** (Default) | **78.9%** | 30/38 | 8/38 | 0 |
| **0.66** | **86.8%** | 33/38 | 5/38 | 0 |
| **0.67** | **89.5%** | 34/38 | 4/38 | 0 |
| **0.68** | **89.5%** | 34/38 | 4/38 | 0 |
| **0.69** | **89.5%** | 34/38 | 4/38 | 0 |
| **0.70** | **92.1%** | 35/38 | 3/38 | 0 |
| **0.71** | **92.1%** | 35/38 | 3/38 | 2 |
| **0.72** | **92.1%** | 35/38 | 3/38 | 2 |
| **0.73** | **92.1%** | 35/38 | 3/38 | 3 |
| **0.74** | **92.1%** | 35/38 | 3/38 | 3 |
| **0.75** | **92.1%** | 35/38 | 3/38 | 3 |

---

## 3. Detailed Failure Analysis & Observations

All 38 evaluation items passed successfully. Zero errors or factual hallucinations observed.

