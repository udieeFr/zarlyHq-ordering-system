# Quick Deployment Checklist

**📍 CURRENT STATUS:** Waiting for DNS propagation (Domain → Lightsail)  
**Domain:** zarlybigfood.my  
**Progress:** ~15% complete (4 major sections to go)

---

## ⏳ WHILE WAITING FOR DNS (5-30 minutes)

Do these things in parallel while DNS propagates:
1. **Configure Lightsail Firewall** (3 min)
   - Open port 80 (HTTP)
   - Open port 443 (HTTPS)
   - Keep SSH (22) - optional: restrict to your IP
2. **Download SSH Key** (2 min)
   - Download from Lightsail console
   - Save to `~/.ssh/lightsail.pem`
   - Run: `chmod 600 ~/.ssh/lightsail.pem`
3. **Review `.env.prod`** (5 min)
   - Check all values are correct
   - Stripe test keys ready
   - Database password set
4. **Test DNS Resolution** (1 min, repeat until it works)
   - `nslookup zarlybigfood.my` should show your Lightsail IP
   - If it doesn't work yet, wait 5 more minutes and retry

---

Use this checklist when deploying to AWS Lightsail. Complete each step in order.

## Understanding Docker First
- [ ] Read "Understanding Docker" section in DEPLOYMENT.md
- [ ] Understand: Image = blueprint, Container = running app
- [ ] Understand: App runs EXACTLY same on PC and VPS
- [ ] Understand: `docker-compose up -d` = deploy everything at once

## Pre-Deployment (Local)
- [ ] All code committed to git
- [ ] No sensitive data in .env (should be in .env.prod only)
- [ ] Tests passing locally
- [ ] Dockerfile builds successfully: `docker build -t zarlyos .`
- [ ] docker-compose works locally: `docker-compose ps` shows no errors

## Create Stripe Account (Today)
- [ ] Go to stripe.com and sign up (5 min)
- [ ] Verify email
- [ ] Fill in personal info (your name, MyKad number)
- [ ] Fill in business info:
  - [ ] Business name: "Your Name" or "Your Name - ZarlyHQ"
  - [ ] Type: Sole Proprietor
  - [ ] Website: your-domain.com
- [ ] Get test API keys from Developers → API Keys
  - [ ] Copy `sk_test_...` (Secret Test Key)
  - [ ] Copy `pk_test_...` (Publishable Test Key)
- [ ] **IMPORTANT**: Deploy with TEST keys first (not live)
- [ ] Apply for live mode (takes 1-7 days, do this while testing)

## AWS Lightsail Setup
- [x] Lightsail instance created (Ubuntu 24.04, 2GB RAM, $12/month) - ✅ DONE
- [x] Static IP allocated and noted - ✅ DONE
- [ ] Firewall configured (80, 443, 22 only) - ⏳ TODO
- [ ] SSH key saved locally: `~/.ssh/lightsail.pem` - ⏳ TODO
- [ ] Can SSH into instance: `ssh -i ~/.ssh/lightsail.pem ubuntu@<ip>` - ⏳ TODO

## Domain Setup
- [x] Domain purchased (zarlybigfood.my) - ✅ DONE
- [x] A record created pointing to Lightsail static IP - ✅ DONE
- [ ] DNS propagated (test with `nslookup zarlybigfood.my`) - ⏳ WAITING (5-30 min)
- [ ] Updated `ALLOWED_HOSTS` in `.env.prod` with your domain

## Server Environment
- [ ] SSH into Lightsail instance
- [ ] System updated: `sudo apt update && sudo apt upgrade -y`
- [ ] Docker installed: `curl -fsSL https://get.docker.com | sh`
- [ ] Docker Compose installed
- [ ] Nginx installed: `sudo apt install nginx -y`
- [ ] Certbot installed: `sudo apt install certbot python3-certbot-nginx -y`

## Application Deployment (With Test Stripe)
- [ ] Repository cloned: `git clone https://github.com/your/repo.git`
- [ ] `.env.prod` created with test values:
  - [ ] SECRET_KEY = new random value
  - [ ] ALLOWED_HOSTS = your domain
  - [ ] DEBUG = False
  - [ ] Database password changed (strong password)
  - [ ] **STRIPE_SECRET_KEY = sk_test_...** (TEST key, not live)
  - [ ] **STRIPE_PUBLISHABLE_KEY = pk_test_...** (TEST key, not live)
- [ ] Docker image built: `docker-compose build`
- [ ] Migrations run: `docker-compose run --rm django python manage.py migrate`
- [ ] Superuser created: `docker-compose run --rm django python manage.py createsuperuser`
- [ ] Static files collected: `docker-compose run --rm django python manage.py collectstatic --noinput`

## SSL/HTTPS Setup
- [ ] `nginx.conf` updated with your domain name
- [ ] Nginx reloaded: `sudo systemctl reload nginx`
- [ ] Certbot certificate generated: `sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com`
- [ ] Certificate paths in nginx.conf point to correct location
- [ ] Nginx restarted: `sudo systemctl restart nginx`
- [ ] Certificate auto-renewal verified: `sudo certbot renew --dry-run`

## Services Running (Test Mode)
- [ ] Docker Compose started: `docker-compose up -d`
- [ ] All containers healthy:
  - [ ] `docker-compose ps` shows all running
  - [ ] Health checks passing
- [ ] Logs checked: `docker-compose logs -f` (no errors)
- [ ] Django logs look good: `docker-compose logs django`
- [ ] Nginx logs look good: `docker-compose logs nginx`

## Testing (With Test Stripe Card)
- [ ] Website loads: `https://your-domain.com`
- [ ] HTTP redirects to HTTPS
- [ ] Login page accessible
- [ ] Sign up works (create test customer)
- [ ] Admin panel accessible: `https://your-domain.com/admin`
- [ ] Static files loaded (CSS/JS visible)
- [ ] **Test order with Stripe test card: `4242 4242 4242 4242`**
  - [ ] Any future date (e.g., 12/25)
  - [ ] Any 3-digit CVC (e.g., 123)
  - [ ] Order creates successfully
  - [ ] No real charge (TEST mode)
- [ ] Database contains test data

## Switch to Live Stripe (After Approval)
- [ ] Wait for Stripe live approval (1-7 days)
- [ ] Get live API keys from Stripe dashboard
- [ ] Update `.env.prod`:
  - [ ] **STRIPE_SECRET_KEY = sk_live_...** (LIVE key)
  - [ ] **STRIPE_PUBLISHABLE_KEY = pk_live_...** (LIVE key)
- [ ] Restart Django: `docker-compose restart django`
- [ ] Verify Stripe keys took effect (should see "Live" in dashboard)
- [ ] **Now accepting real payments** ✅

## Security Checklist
- [ ] DEBUG = False in production
- [ ] SECRET_KEY is unique (not from template)
- [ ] Database password strong (12+ chars, mixed case, numbers)
- [ ] .env file NOT committed to git
- [ ] SSH password disabled (key-only auth)
- [ ] Firewall restricts SSH to your IP only (optional)
- [ ] SSL certificate valid (not self-signed)
- [ ] Rate limiting configured in Nginx
- [ ] ALLOWED_HOSTS matches your domain exactly
- [ ] Using test Stripe keys for testing ✅
- [ ] Only switch to live keys after testing ✅

## Post-Deployment
- [ ] Set up automatic backups (optional)
- [ ] Configure monitoring (optional: Cloudflare, New Relic)
- [ ] Test order notification emails
- [ ] Document deployment for future reference
- [ ] Plan for database growth and scaling

---

## Useful Commands

```bash
# SSH into server
ssh -i ~/.ssh/lightsail.pem ubuntu@<your-static-ip>

# View all running containers
docker-compose ps

# View logs (all services)
docker-compose logs -f

# View specific service logs
docker-compose logs -f django
docker-compose logs -f nginx
docker-compose logs -f db

# Restart all services
docker-compose restart

# Stop all services
docker-compose down

# Start all services
docker-compose up -d

# Run Django commands
docker-compose run --rm django python manage.py <command>

# Database backup
docker-compose exec db pg_dump -U postgres zarlyos > backup.sql

# Database restore
docker-compose exec -T db psql -U postgres zarlyos < backup.sql

# Check SSL certificate
echo | openssl s_client -servername your-domain.com -connect your-domain.com:443 2>/dev/null | openssl x509 -noout -dates

# Renew SSL certificate
sudo certbot renew --force-renewal
docker-compose restart nginx

# Check DNS resolution
nslookup your-domain.com
dig your-domain.com
```

---

## Troubleshooting Quick Links

### Django won't start?
1. Check logs: `docker-compose logs django`
2. Verify .env.prod has all required variables
3. Check database connection: `docker-compose logs db`
4. Restart: `docker-compose restart django`

### Nginx not proxying?
1. Check logs: `docker-compose logs nginx`
2. Test Nginx syntax: `sudo nginx -t`
3. Verify django is running: `docker-compose ps django`
4. Restart: `docker-compose restart nginx`

### SSL certificate not renewing?
1. Test renewal: `sudo certbot renew --dry-run`
2. Check Certbot logs: `sudo journalctl -u certbot.timer`
3. Force renew: `sudo certbot renew --force-renewal`
4. Reload Nginx: `sudo systemctl reload nginx`

### Out of memory?
1. Check usage: `free -h` and `docker stats`
2. Upgrade Lightsail plan ($12 → $20)
3. OR restart services to clear memory: `docker-compose restart`

### Database connection issues?
1. Verify DB is running: `docker-compose ps db`
2. Check DB health: `docker-compose logs db`
3. Test connection: `docker-compose exec db psql -U postgres -d zarlyos -c "SELECT 1"`

---

## Support

See full deployment guide: `DEPLOYMENT.md`
See domain setup guide: `DOMAIN_SETUP.md`
See environment template: `.env.prod.example`
