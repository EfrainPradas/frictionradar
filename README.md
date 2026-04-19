# Friction Radar MVP

Internal tool to analyze companies and detect public signals of operational friction.

## 📁 Project Architecture

- **Backend**: FastAPI (Python), handling data collection, routing, scoring, and hypotheses.
- **Frontend**: React + TypeScript + Vite, an Analyst Console.
- **Database**: Supabase (PostgreSQL), relational schema for companies, signals, and scores.

## 🚀 Setup Instructions

### 1. Database Setup
Execute the SQL schema found in `infra/supabase/schema.sql` on your Supabase instance.
*Or*, if you provided your DB password, run migrations normally.

### 2. Backend Setup
```bash
cd backend
python -m venv venv
# On Windows: venv\Scripts\activate
# On Mac/Linux: source venv/bin/activate
pip install -r requirements.txt

# Create .env based on .env.example
copy .env.example .env

# Run FastAPI Server
uvicorn main:app --reload
```
The backend will run on http://localhost:8000

### 3. Frontend Setup
```bash
cd frontend
npm install

# Run Vite Dev Server
npm run dev
```

## 🧪 Testing the Pipeline (Phase 2)

Once your local server is running, you can seed and test the pipeline using curl (or Postman/ThunderClient).

### Step 1: Create a Company
```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/companies/' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "name": "Stripe",
  "domain": "stripe.com",
  "industry": "Fintech"
}'
```
*Note the returned `id` (e.g., `123e4567-e89b-12d3...`).*

### Step 2: Trigger the Collector Pipeline
```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/companies/<YOUR_UUID_HERE>/collect' \
  -H 'accept: application/json'
```
*This triggers the BackgroundTask across the multiple targeted extractors.*

### Step 3: Check Collection Runs Status
```bash
curl -X 'GET' \
  'http://localhost:8000/api/v1/companies/<YOUR_UUID_HERE>/collection-runs' \
  -H 'accept: application/json'
```

### Step 4: Extract the Signals Collected
```bash
curl -X 'GET' \
  'http://localhost:8000/api/v1/companies/<YOUR_UUID_HERE>/signals' \
  -H 'accept: application/json'
```

## 🧠 Testing the Intelligence Layer (Phase 3)

After the Phase 2 pipeline, the scoring and hypothesis endpoints are now live.

### Step 5: Compute Friction Score
```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/companies/<YOUR_UUID_HERE>/score' \
  -H 'accept: application/json'
```
Returns a full JSON breakdown like:
```json
{
  "total_score": 4.5,
  "dominant_friction_type": "reporting_fragmentation",
  "scoring_breakdown_json": {
    "reporting_fragmentation": { "score": 2.5, "matched_signals": ["analytics_role_detected"] },
    ...
  }
}
```

### Step 6: Generate Opportunity Hypothesis
```bash
curl -X 'POST' \
  'http://localhost:8000/api/v1/companies/<YOUR_UUID_HERE>/hypothesis' \
  -H 'accept: application/json'
```

### Step 7: Get Latest Score and Hypothesis
```bash
curl 'http://localhost:8000/api/v1/companies/<UUID>/scores/latest'
curl 'http://localhost:8000/api/v1/companies/<UUID>/hypotheses/latest'
```

## 🚧 Status
- [x] Foundation scaffolded.
- [x] Real Database Schema and ORM Pipeline built.
- [x] FastAPI Signals architecture enabled.
- [x] Rule-based Scoring Engine and Hypothesis Generator implemented.
- [ ] Frontend Analyst Console pending.
