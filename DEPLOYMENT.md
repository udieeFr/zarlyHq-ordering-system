# ZarlyHQ Deployment Guide

Complete guide for deploying ZarlyHQ to AWS Lightsail with Docker, PostgreSQL, and Let's Encrypt SSL.

## Table of Contents
1. [Understanding Docker](#understanding-docker)
2. [Prerequisites](#prerequisites)
3. [AWS Lightsail Setup](#aws-lightsail-setup)
4. [Domain Configuration](#domain-configuration)
5. [Stripe Account Setup](#stripe-account-setup)
6. [Server Environment Setup](#server-environment-setup)
7. [Docker Setup](#docker-setup)
8. [SSL/HTTPS Setup](#sslhttps-setup)
9. [Deployment](#deployment)
10. [Testing](#testing)
11. [Monitoring & Maintenance](#monitoring--maintenance)

---

## Understanding Docker

### What is Docker?

Docker is a **containerization platform** that packages your entire application with all dependencies into a portable unit. Think of it like:

```
Your PC (Windows)          VPS (Linux)
├─ Python 3.11            ├─ Python 3.11 (in container)
├─ Django 6.0             ├─ Django 6.0 (in container)
├─ PostgreSQL 17          ├─ PostgreSQL 17 (in container)
├─ Nginx                  ├─ Nginx (in container)
└─ All packages           └─ All packages (in container)

Result: App runs EXACTLY the same on both ✅
```

### Key Concepts

**Image** = Blueprint/Recipe
- Defines everything needed (Python version, all packages, code, configuration)
- Created by `Dockerfile`
- Portable and shareable

**Container** = Running Instance
- Created from an image
- Like a lightweight virtual computer
- App runs inside the container

**Docker Compose** = Multi-Container Orchestrator
- Manages multiple containers (Django + PostgreSQL + Nginx)
- They communicate on a private network
- All configured in `docker-compose.yml`

### How It Solves "Works on My Machine"

**Without Docker:**
```
PC: Python 3.10, PostgreSQL 14 → Works ✅
VPS: Python 3.11, PostgreSQL 17 → Broken ❌
```

**With Docker:**
```
PC: Container with Python 3.11, PostgreSQL 17 → Works ✅
VPS: Same container with Python 3.11, PostgreSQL 17 → Works ✅
```

### Deployment Workflow

```
1. You write code on PC
2. Docker builds image (Dockerfile → zarlyos:v1)
3. Push image to Docker Hub or keep locally
4. VPS pulls image and runs it
5. App works EXACTLY as it ran on your PC
```

### Why This Matters for You

- **No more setup pain**: Instead of installing 10 things on VPS, just `docker-compose up -d`
- **Guaranteed consistency**: Works same on PC, VPS, and cloud
- **Easy updates**: Change code, rebuild image, deploy new version
- **Easy rollback**: Keep old image versions, switch back if needed

---

## Stripe Account Setup

### Test Mode vs Live Mode

You have **2 modes** on the same Stripe account:

**Test Mode** (Immediate)
- Available immediately after signup (5 minutes)
- Use test API keys: `sk_test_...`, `pk_test_...`
- Use test cards: `4242 4242 4242 4242` (no real charges)
- Test full order flow → checkout → "payment"
- **No money changes hands**

**Live Mode** (1-7 days)
- Need to apply and get approved
- Use live API keys: `sk_live_...`, `pk_live_...`
- Accept real customer payments
- Real money goes to your bank account

### Timeline Recommendation

**Do NOT wait for live mode before deploying.** Deploy with test mode:

| When | Task | Time |
|------|------|------|
| **Today** | Buy domain + VPS | 15 min |
| **Today** | Deploy with test Stripe keys | 1 hour |
| **Today** | Create live Stripe account (apply) | 5 min signup |
| **Today-7 days** | Stripe reviews your application | Background |
| **After approval** | Swap test keys → live keys | 2 min |

### Personal/Sole Proprietor Account

You **do NOT need a formal business** to use Stripe. You can register as:

**Sole Proprietor** (Perfect for startups)
- Use your personal name
- Use your personal ID (MyKad for Malaysia)
- Use your personal bank account
- Business type: "Sole Proprietor"

**What Stripe Will Ask:**
```
Business Info:
- Business name: "Your Name" or "Your Name - ZarlyHQ"
- Business type: ⭕ Sole Proprietor
- Website: your-domain.com
- What you do: "Food ordering platform"
- Annual revenue: (your estimate)

Personal Info:
- Your full name
- Your ID number (MyKad)
- Your personal bank account
- Your home address
```

### For Malaysia (Specific)

- **MyKad**: Works as ID (have it ready)
- **Bank Account**: Any Malaysian bank account (personal is fine)
- **Optional**: Can register SSM business later if you scale
- **Registration**: Not needed to start, but good to formalize after 6 months

### Step-by-Step Stripe Setup

1. Go to **stripe.com**
2. Click **Start Now**
3. Sign up with email
4. Verify email (check inbox)
5. Fill in personal info:
   - Name
   - Email
   - Phone
6. Fill in business info:
   - Business name (can be your name)
   - Website (your domain)
   - Type: Sole Proprietor
7. For live mode (after deployment), submit:
   - ID (MyKad)
   - Bank account
   - Address
8. Wait 1-7 days for approval

### Get API Keys

After signup:
1. Go to Stripe Dashboard
2. Click **Developers** (left menu)
3. Click **API Keys**
4. You'll see 4 keys:
   - `pk_test_...` (Publishable Test Key)
   - `sk_test_...` (Secret Test Key)
   - `pk_live_...` (appears after approval)
   - `sk_live_...` (appears after approval)

### Deploy Timeline with Stripe

```bash
# Today: Deploy with test keys
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...

# Test with 4242 4242 4242 4242 card
# Order → Checkout → Success → Order created ✅

# Background: Stripe approves your live application (1-7 days)

# After approval: Update .env.prod
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...

# Restart container
docker-compose restart django

# Now accepting real payments ✅
```

---

## Prerequisites

### What You Need
- AWS account (free, pay per usage)
- Domain name (buy separately)
- Git repository access
- SSH client (built-in on Mac/Linux, use PuTTY on Windows)
- Basic Linux/command-line knowledge
- **Stripe account** (free, sign up first)

### Cost Estimate (Monthly)
- Lightsail instance (Ubuntu 24.04, 2GB RAM): **$12/month**
- Static IP: **Included (first 3 free)**
- Let's Encrypt SSL: **Free**
- Domain: **~$10-15/month** (one-time yearly, ~$1/month avg)
- Stripe fees: **2.9% + 30¢ per transaction** (only when customers pay)
- **Total: ~$22-25/month** (before Stripe transaction fees)

### What's Already Prepared

All Docker and Nginx files are in your repository:
- ✅ `Dockerfile` - Production image definition
- ✅ `docker-compose.yml` - Multi-container orchestration
- ✅ `nginx.conf` - Reverse proxy configuration
- ✅ `gunicorn_config.py` - WSGI server configuration
- ✅ `.env.prod.example` - Environment template
- ✅ `requirements.txt` - Python dependencies (with gunicorn)

---

## AWS Lightsail Setup

### Step 1: Launch Lightsail Instance

1. Go to **AWS Console** → **Lightsail**
2. Click **Create instance**
3. Choose:
   - **Platform**: Linux/Unix
   - **Blueprint**: Ubuntu 24.04 LTS
   - **Instance Plan**: $12/month (2GB RAM, 1 vCPU, 60GB SSD)
   - **Instance Name**: `zarlyos-prod` (or your choice)
4. Click **Create instance**
5. Wait 2-3 minutes for instance to start

### Step 2: Allocate Static IP

1. In Lightsail, click **Networking**
2. Click **Create static IP**
3. Attach to your instance
4. Note the static IP address (e.g., `54.123.45.67`)

### Step 3: Configure Firewall

1. In Lightsail instance details, click **Networking**
2. Under "Firewall", add rules:
   - **SSH** (22): Source = Your IP only (for security)
   - **HTTP** (80): Source = 0.0.0.0/0
   - **HTTPS** (443): Source = 0.0.0.0/0
   - **PostgreSQL** (5432): Source = None (internal only)

### Step 4: SSH into Instance

```bash
# Download SSH key from Lightsail console
# Save as ~/.ssh/lightsail.pem
chmod 600 ~/.ssh/lightsail.pem

# Connect
ssh -i ~/.ssh/lightsail.pem ubuntu@<your-static-ip>

# Update system
sudo apt update && sudo apt upgrade -y
```

---

## Domain Configuration

### Step 1: Buy a Domain

Choose a registrar:
- GoDaddy, Namecheap, Route 53, Google Domains, etc.
- Typical cost: $10-15/year

**Example domain**: `zarly.com.my` (or your choice)

### Step 2: Point Domain to Lightsail

In your domain registrar, set **A record**:
- **Name**: `@` (root domain)
- **Type**: `A`
- **Value**: Your Lightsail static IP (`54.123.45.67`)

**Optional: Add www subdomain**
- **Name**: `www`
- **Type**: `A`
- **Value**: Your Lightsail static IP

DNS propagation takes 5-30 minutes.

### Step 3: Test DNS Resolution

```bash
# Should resolve to your Lightsail IP
nslookup zarly.com.my
ping zarly.com.my
```

---

## Server Environment Setup

### SSH into Instance

```bash
ssh -i ~/.ssh/lightsail.pem ubuntu@52.220.39.92
```

Replace `52.220.39.92` with your actual Lightsail static IP.

### Update System

```bash
sudo apt update && sudo apt upgrade -y
```

### Install Docker

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu
```

### Install Docker Compose

```bash
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Verify Installation

```bash
docker --version
docker-compose --version
```

### Log Out and Back In (For Docker Permission Changes)

```bash
exit
# SSH back in
ssh -i ~/.ssh/lightsail.pem ubuntu@52.220.39.92
```

### Install Certbot (Let's Encrypt SSL)

```bash
sudo apt install certbot -y
```

---

## Application Deployment

### Step 1: Clone Repository

```bash
cd /home/ubuntu
git clone https://github.com/yourusername/ZarlyHQ.git
cd ZarlyHQ
```

### Step 2: Create .env File for Production

Copy `.env.prod.example` or create `.env` with production values:

```bash
# Copy template (if exists)
cp .env.prod.example .env
# OR create new .env file with values from .env.prod locally
```

**Production .env must contain:**

```
DEBUG=False
SECRET_KEY=<generate-new-random-key>
ALLOWED_HOSTS=zarlybigfood.my,www.zarlybigfood.my
DB_NAME=zarlyos
DB_USER=postgres
DB_PASSWORD=<your-strong-password>
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_test_...
FERNET_KEY=<your-fernet-key>
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
```

**Generate SECRET_KEY:**
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

**Generate FERNET_KEY:**
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Step 3: Build Docker Image

```bash
docker-compose build
```

This builds the Django image using the Dockerfile with Python 3.12.

### Step 4: Run Migrations

```bash
docker-compose run --rm django python manage.py migrate
```

### Step 5: Create Superuser

```bash
docker-compose run --rm django python manage.py createsuperuser
```

Follow prompts to create admin account.

### Step 6: Collect Static Files

```bash
docker-compose run --rm django python manage.py collectstatic --noinput
```

### Step 7: Start All Services

```bash
docker-compose up -d
```

### Step 8: Verify Services are Running

```bash
# Check all containers
docker-compose ps

# Should show:
# - zarlyos-db (healthy)
# - zarlyos-app (running)
# - zarlyos-web (running)
```

### Step 9: Check Logs

```bash
# View Django logs
docker-compose logs django

# View Nginx logs
docker-compose logs nginx

# View all logs
docker-compose logs -f
```

---

## SSL Certificate Setup

### Step 1: Update Nginx Config

Edit `nginx.conf` and update:
- Line 66: Change `server_name localhost;` to `server_name zarlybigfood.my www.zarlybigfood.my;`
- Line 69-70: Uncomment the Let's Encrypt paths
- Line 73-74: Comment out the self-signed cert paths

```nginx
# Line 66 - Update server names
server_name zarlybigfood.my www.zarlybigfood.my;

# Line 68-70 - Uncomment Let's Encrypt (comment lines 73-74)
ssl_certificate /etc/letsencrypt/live/zarlybigfood.my/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/zarlybigfood.my/privkey.pem;
```

### Step 2: Generate SSL Certificate

```bash
# Stop Nginx briefly for certificate generation
docker-compose stop nginx

# Generate certificate
sudo certbot certonly --standalone -d zarlybigfood.my -d www.zarlybigfood.my

# Start Nginx with new certificate
docker-compose start nginx
```

### Step 3: Verify Certificate

```bash
sudo certbot certificates
```

Should show your domain and certificate details.

### Step 4: Test Certificate Auto-Renewal

```bash
sudo certbot renew --dry-run
```

---

## Testing

### Test 1: Website Loads

```bash
# Check HTTP → HTTPS redirect
curl -I http://zarlybigfood.my

# Should return: HTTP/1.1 301 Moved Permanently
# Location: https://zarlybigfood.my

# Check HTTPS works
curl -I https://zarlybigfood.my
```

### Test 2: Admin Panel

Open browser: `https://zarlybigfood.my/admin`
- Login with superuser credentials
- Verify admin panel works

### Test 3: Create Test Order

1. Open `https://zarlybigfood.my` in browser
2. Sign up as customer
3. Browse products
4. Add items to cart
5. Proceed to checkout
6. Use Stripe test card: `4242 4242 4242 4242`
   - Any future date (e.g., 12/25)
   - Any 3-digit CVC (e.g., 123)
7. Click "Pay"
8. Order should succeed (no real charge, test mode)

### Test 4: Check SSL Certificate

```bash
echo | openssl s_client -servername zarlybigfood.my -connect zarlybigfood.my:443 2>/dev/null | openssl x509 -noout -dates
```

Should show valid certificate dates.

---

## Monitoring

### View Container Status

```bash
docker-compose ps
docker stats
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f django
docker-compose logs -f nginx
docker-compose logs -f db
```

### Database Check

```bash
# Test database connection
docker-compose exec db psql -U postgres -d zarlyos -c "SELECT 1"
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart django
docker-compose restart nginx
docker-compose restart db
```

---

## Switching to Live Stripe Keys

After Stripe approves your account (1-7 days):

1. Get live API keys from Stripe Dashboard
2. Update `.env`:
   ```
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_PUBLISHABLE_KEY=pk_live_...
   ```
3. Restart Django:
   ```bash
   docker-compose restart django
   ```
4. Now accepting real payments

---

## Monitoring & Maintenance

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f django
docker-compose logs -f nginx
docker-compose logs -f db
```

### Database Backup

```bash
# Backup
docker-compose exec db pg_dump -U postgres zarlyos > backup.sql

# Restore
docker-compose exec -T db psql -U postgres zarlyos < backup.sql
```

### Update Application

```bash
cd /home/ubuntu/ZarlyHQ

# Pull latest code
git pull origin main

# Rebuild image
docker-compose build

# Restart services
docker-compose up -d

# Run migrations if needed
docker-compose run --rm django python manage.py migrate
```

### System Health

```bash
# Check resource usage
docker stats

# Disk space
df -h

# Memory
free -h

# Nginx status
sudo systemctl status nginx
```

### SSL Certificate Renewal

Certbot automatically renews 30 days before expiration. Verify:

```bash
sudo certbot renew --dry-run
```

---

## Troubleshooting

### Certificate Issues

```bash
# Renew immediately
sudo certbot renew --force-renewal

# Rebuild Nginx with new cert
docker-compose restart nginx
```

### Database Connection Error

```bash
# Check if DB is running
docker-compose ps db

# Check DB logs
docker-compose logs db

# Restart DB
docker-compose restart db
```

### Out of Memory

```bash
# Check memory usage
free -h
docker stats

# Increase Lightsail plan or optimize app
```

### Port Already in Use

```bash
# Find process using port 80 or 443
sudo lsof -i :80
sudo lsof -i :443

# Kill and restart
docker-compose restart nginx
```

---

## Security Checklist

- [ ] Domain configured with Lightsail IP
- [ ] SSL certificate installed and auto-renewing
- [ ] ALLOWED_HOSTS set to your domain
- [ ] DEBUG=False in production
- [ ] Secret key rotated (new random value)
- [ ] Database password strong (not default)
- [ ] SSH key-only authentication enabled
- [ ] Firewall restricts SSH to your IP
- [ ] Stripe test keys (not live) used initially
- [ ] Static files collected
- [ ] Admin panel secured (strong password)
- [ ] Backup strategy in place

---

## Cost Optimization

- **Lightsail $12/month**: Adequate for small-medium traffic
- **Scale to $20/month** if you need more resources
- **Add monitoring** if traffic exceeds capacity
- **Consider CloudFlare** for DDoS protection (free tier available)

---

## Next Steps

1. Buy domain
2. Launch Lightsail instance
3. Follow steps 1-8 above
4. Monitor logs and performance
5. Set up regular backups
6. Plan database scaling strategy

