# jmeter-fhir-performance

Apache JMeter load tests for a **FHIR R4** healthcare API ([HAPI FHIR](https://hapifhir.io/)), with a CI performance gate in GitHub Actions.

FHIR is the HL7 standard API that EHR/EMR systems expose for patient records. This repo simulates clinic users working through a patient journey and fails the build when latency or error rate crosses a threshold.

## What it tests

One JMeter thread = one clinic user looping through this journey:

| Transaction | Requests | Checks |
|---|---|---|
| TX01 Register patient | `POST /Patient` | 201, `resourceType = Patient`, extracts `patientId` |
| TX02 Read patient | `GET /Patient/{id}` | 200, returned `id` matches |
| TX03 Update patient | `PUT /Patient/{id}` (adds a phone number) | 200, telecom present |
| TX04 Search patients by family name | `GET /Patient?family=…` | 200, `Bundle` |
| TX05 Record heart-rate observation | `POST /Observation` (LOINC 8867-4, linked to the patient) | 201, subject reference matches, extracts `observationId` |
| TX06 Read patient vitals history | `GET /Observation?subject=Patient/{id}` | 200, `Bundle` |
| TX07 Clean up test data | `DELETE /Observation/{id}`, `DELETE /Patient/{id}` | 200/204 |

All patient data is synthetic (`data/patients.csv`). Every created patient carries the identifier system `urn:jmeter-fhir-performance`. Each iteration deletes what it created, and a **tearDown thread group** removes anything left by threads the duration timer stopped mid-journey, so a run leaves zero test data on the server.

## JMeter techniques used

| Technique | Where |
|---|---|
| Parameterized load profiles (`__P` properties, `-q` files) | `profiles/*.properties` |
| HTTP Request Defaults + Header Manager (`application/fhir+json`) | top of the plan |
| CSV Data Set Config (shared, recycled) | `Synthetic patients` |
| **Correlation**: JSON Extractor pulls server-generated IDs into later requests | TX01, TX05 |
| Response, JSON Path and Duration assertions | every sampler; per-request SLA via `slaMs`. JSON Path assertions use anchored regex, because exact-match mode fails numeric-looking FHIR ids (`"101252"`) |
| Transaction Controllers for per-flow percentiles | TX01–TX07 |
| Think time (Uniform Random Timer) | thread group |
| tearDown Thread Group + ForEach controllers + multi-match JSON extraction | `tearDown: delete leftover test data` |
| Non-GUI execution + HTML dashboard (`-n -e -o`) | `scripts/run-local.ps1`, CI |
| CI threshold gate on p95 + error rate, with a selftest that proves it can fail | `scripts/check_thresholds.py`, `tests/` |

## Load profiles

| Profile | Users | Ramp-up | Duration | Purpose |
|---|---:|---:|---:|---|
| smoke | 2 | 5 s | 1 min | Plan works end to end |
| load | 20 | 60 s | 5 min | Expected concurrent usage |
| stress | 60 | 120 s | 7 min | Where latency starts to bend |
| spike | 80 | 5 s | 2 min | Recovery from a sudden burst |

## Run it

Requirements: Java 17+, [JMeter 5.6.3](https://jmeter.apache.org/download_jmeter.cgi), Python 3.

**Smoke against the public HAPI test server** (smoke only: it's a shared community server, never load-test it):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-local.ps1
```

**Load against your own HAPI** (`docker run -p 8080:8080 hapiproject/hapi:v8.12.0-2`):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-local.ps1 -Target local -Profile load
```

**Edit the plan in the GUI:** open `test-plans/fhir-patient-journey.jmx` in `jmeter.bat`. Enable the disabled *View Results Tree* listener only while debugging, and run real load in non-GUI mode.

Raw command (what the script and CI run):

```bash
jmeter -n -t test-plans/fhir-patient-journey.jmx -q profiles/load.properties \
  -Jprotocol=http -Jhost=localhost -Jport=8080 -JbasePath=/fhir \
  -l results/results.jtl -e -o results/report
python scripts/check_thresholds.py --stats results/report/statistics.json --thresholds scripts/thresholds.json
```

## CI

`.github/workflows/performance.yml`:

1. `gate-selftest`: unit tests prove the gate fails on slow transactions, high error rate, an empty report, too few samples, and a missing transaction. Thresholds must also match the plan's transaction names.
2. `jmeter`: starts HAPI FHIR as a service container, waits for `/fhir/metadata`, runs the plan, applies the gate, writes a results table to the job summary, and uploads the HTML report.

Pushes and PRs run `smoke`. Run `load`, `stress` or `spike` from **Actions → performance → Run workflow**.

## Thresholds

`scripts/thresholds.json`: max error rate 1%, at least 20 samples, and a p95 limit per transaction. They are starting values, to be recalibrated from the first CI baseline runs.

## Results

_Filled in from CI runs._
