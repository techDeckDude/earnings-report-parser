# AWS Deployment Plan

This document outlines how to migrate the earnings report parser from a local prototype to a production deployment on AWS using S3, EC2, and RDS.

---

## Architecture Overview

```
                        ┌─────────────────────────────────────────────┐
                        │                    VPC                       │
                        │                                              │
  User uploads PDF      │  ┌──────────────┐       ┌───────────────┐  │
  ──────────────────►  S3 │  EC2 Instance │──────►│  RDS Postgres │  │
                        │  │              │       │               │  │
  User views dashboard  │  │  • Flask app │       │  • companies  │  │
  ◄─────────────────── ─┤  │  • main.py   │       │  • reports    │  │
                        │  │  • nginx     │       │  • metrics    │  │
                        │  │  • gunicorn  │       │               │  │
                        │  └──────────────┘       └───────────────┘  │
                        │        │                                     │
                        │        ▼                                     │
                        │  IAM Role: S3 read + RDS access             │
                        └─────────────────────────────────────────────┘
```

### Roles of each service

| Service | Role |
|---|---|
| **S3** | Stores incoming 10-Q PDFs. The user (or an automated process) uploads a PDF here to trigger ingestion. |
| **EC2** | Runs the Flask dashboard and the ingestion script. Pulls PDFs from S3, writes extracted data to RDS. |
| **RDS (PostgreSQL)** | Replaces the local SQLite file. Stores companies, earnings reports, and financial metrics. Persists independently of the EC2 instance. |

---

## What Changes in the Code

The core extraction and validation logic (`extractor.py`, `models.py`) does not change. Only the I/O layer needs updating.

### 1. `db.py` — swap SQLite for PostgreSQL

Replace the `sqlite3` connection with `psycopg2`:

```python
import psycopg2
import os

def get_db():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        port=5432,
    )
```

The schema SQL and all upsert logic stays the same — PostgreSQL supports the same `INSERT ... ON CONFLICT ... DO UPDATE` syntax. Change `?` placeholders to `%s` (psycopg2 style).

### 2. `main.py` — accept S3 URIs as input

Add a step that downloads the PDF from S3 to a temp file before extraction:

```python
import boto3
import tempfile

def download_from_s3(s3_uri: str) -> str:
    """Download s3://bucket/key to a local temp file. Returns the local path."""
    bucket, key = s3_uri.replace("s3://", "").split("/", 1)
    s3 = boto3.client("s3")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        s3.download_fileobj(bucket, key, f)
        return f.name

def run(input_path: str):
    if input_path.startswith("s3://"):
        pdf_path = download_from_s3(input_path)
    else:
        pdf_path = input_path  # local path still works
    # ... rest of pipeline unchanged
```

Usage becomes:
```bash
python main.py s3://your-bucket/filings/2026-Q2-PLTR-10Q.pdf
```

### 3. `app.py` — no logic changes

The Flask app talks to the database through `db.py`, so pointing it at RDS is just a matter of setting environment variables. No code changes needed.

---

## AWS Setup Steps

### Step 1: Create the S3 bucket

```bash
aws s3 mb s3://earnings-report-filings
```

Enable versioning so you can recover overwritten PDFs:
```bash
aws s3api put-bucket-versioning \
  --bucket earnings-report-filings \
  --versioning-configuration Status=Enabled
```

Keep the bucket private — EC2 will access it via an IAM role, not public URLs.

### Step 2: Launch the RDS instance

- **Engine**: PostgreSQL 16
- **Instance class**: `db.t3.micro` (free tier eligible)
- **Storage**: 20 GB gp2
- **VPC**: put it in a **private subnet** — it should not be reachable from the internet, only from EC2
- **Security group**: allow inbound on port 5432 only from the EC2 security group

```bash
aws rds create-db-instance \
  --db-instance-identifier earnings-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 16 \
  --master-username earningsadmin \
  --master-user-password <your-password> \
  --allocated-storage 20 \
  --no-publicly-accessible
```

Note the endpoint hostname once the instance is available — you'll need it as `DB_HOST`.

### Step 3: Create an IAM role for EC2

The EC2 instance needs permission to read from S3 and connect to RDS. Create a role with:

**Policy 1 — S3 read access** (inline or managed):
```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::earnings-report-filings",
    "arn:aws:s3:::earnings-report-filings/*"
  ]
}
```

**Policy 2 — RDS connection** is handled by the security group, not IAM. No additional IAM policy needed for basic password auth.

Attach this role to the EC2 instance at launch (Instance Profile).

### Step 4: Launch the EC2 instance

- **AMI**: Amazon Linux 2023 or Ubuntu 24.04
- **Instance type**: `t3.micro` (free tier) or `t3.small` for more headroom
- **Subnet**: public subnet (so the dashboard is reachable from your browser)
- **Security group**: allow inbound 80/443 from anywhere, 22 (SSH) from your IP only
- **IAM Instance Profile**: the role created in Step 3

After launch, SSH in and set up the environment:

```bash
# Install dependencies
sudo dnf install python3 python3-pip nginx git -y   # Amazon Linux 2023
pip3 install pdfplumber pydantic flask psycopg2-binary boto3 gunicorn

# Clone the repo
git clone <your-repo-url> /home/ec2-user/earnings-report-parser
cd /home/ec2-user/earnings-report-parser

# Set environment variables (add to /etc/environment or use SSM Parameter Store)
export DB_HOST=<rds-endpoint>
export DB_NAME=earningsdb
export DB_USER=earningsadmin
export DB_PASSWORD=<your-password>

# Initialize the database schema
python3 -c "from db import init_db; init_db()"
```

### Step 5: Run the database schema migration

The first time you connect, run the schema creation:

```bash
python3 -c "from db import init_db; init_db()"
```

This creates the `companies`, `earnings_reports`, and `financial_metrics` tables in RDS. Subsequent runs are idempotent (`CREATE TABLE IF NOT EXISTS`).

### Step 6: Serve the Flask app with gunicorn + nginx

**gunicorn** (start and keep running):
```bash
gunicorn --bind 0.0.0.0:5001 --workers 2 --daemon app:app
```

Or create a systemd service so it starts on reboot:
```ini
# /etc/systemd/system/earnings-dashboard.service
[Unit]
Description=Earnings Dashboard
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/earnings-report-parser
EnvironmentFile=/etc/earnings.env
ExecStart=/usr/local/bin/gunicorn --bind 0.0.0.0:5001 --workers 2 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

**nginx** reverse proxy (so the dashboard is on port 80):
```nginx
# /etc/nginx/conf.d/earnings.conf
server {
    listen 80;
    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
    }
}
```

```bash
sudo systemctl enable --now earnings-dashboard nginx
```

---

## Ingestion Workflow (Post-Deployment)

Once deployed, the process to ingest a new filing is:

```
1. Upload PDF to S3
   aws s3 cp "2026 Q3 PLTR 10-Q.pdf" s3://earnings-report-filings/

2. SSH into EC2 and run main.py
   python3 main.py s3://earnings-report-filings/2026 Q3 PLTR 10-Q.pdf

3. Reload the dashboard in your browser — new row appears automatically
   http://<ec2-public-ip>
```

A future improvement would be to trigger step 2 automatically via an S3 event notification → Lambda → EC2 SSM Run Command, removing the SSH step entirely.

---

## Environment Variables Reference

Store these in `/etc/earnings.env` on the EC2 instance (restrict file permissions to `600`):

| Variable | Description |
|---|---|
| `DB_HOST` | RDS endpoint hostname |
| `DB_NAME` | Database name (e.g. `earningsdb`) |
| `DB_USER` | Master username |
| `DB_PASSWORD` | Master password |
| `AWS_DEFAULT_REGION` | e.g. `us-east-1` (used by boto3 if not set via instance metadata) |

---

## Cost Estimate (us-east-1, light usage)

| Service | Config | Estimated monthly cost |
|---|---|---|
| EC2 | t3.micro, on-demand | ~$8.50 (free tier: $0 for 12 months) |
| RDS | db.t3.micro, 20 GB gp2 | ~$15 (free tier: $0 for 12 months) |
| S3 | < 1 GB storage + minimal requests | < $0.25 |
| **Total** | | **~$24/month** (or $0 in free tier year) |

---

## What Is Not Covered Here

- **HTTPS / TLS**: add an ACM certificate + Application Load Balancer, or use Certbot on the EC2 instance for a self-signed cert
- **Secrets management**: move DB credentials from a flat env file to AWS Secrets Manager or SSM Parameter Store
- **Automated ingestion trigger**: S3 event → Lambda to eliminate the SSH step
- **Multi-AZ RDS**: enable for production durability (doubles RDS cost)
