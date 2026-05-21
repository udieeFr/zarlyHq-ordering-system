# ZarlyHQ Deployment Guide

Deploy ZarlyHQ to AWS Lightsail using pre-built Docker images pulled from Docker Hub.

## How It Works

```
Your PC
  └─ docker build → docker push → Docker Hub (udieefr/zarlyhq:latest)

VPS (Lightsail)
  └─ 3 files only: docker-compose.yml + .env + nginx.conf
  └─ docker-compose up -d  ← pulls image + starts everything
```

No repo clone on the VPS. No building. Just pull and run.

---

## Stack

| Container | Image | Role |
|---|---|---|
| zarlyos-app | `udieefr/zarlyhq:latest` (your app) | Django + Gunicorn |
| zarlyos-db | `postgres:17` (official) | Database |
| zarlyos-web | `nginx:alpine` (official) | Reverse proxy + SSL |

---

## Checklist

### Phase 1 — Before Touching the VPS

- [ ] Push latest image to Docker Hub
  ```bash
  docker build -t udieefr/zarlyhq:latest .
  docker push udieefr/zarlyhq:latest
  ```
- [ ] Buy domain (e.g. `zarlybigfood.my`) — ~RM 50/year
- [ ] Sign up for Stripe at stripe.com (5 min)
- [ ] Sign up for AWS at aws.amazon.com (free account)

---

### Phase 2 — AWS Lightsail Setup

- [ ] Go to **AWS Console → Lightsail → Create instance**
  - Platform: Linux/Unix
  - Blueprint: Ubuntu 24.04 LTS
  - Plan: **$12/month** (2GB RAM, 1 vCPU, 60GB SSD)
  - Name: `zarlyos-prod`
- [ ] Click **Networking → Create static IP** → attach to instance
- [ ] Note down your static IP (e.g. `54.123.45.67`)
- [ ] Under **Networking → Firewall**, add rules:
  - SSH (22) — Your IP only
  - HTTP (80) — Anywhere
  - HTTPS (443) — Anywhere

---

### Phase 3 — Domain Setup

- [x] In your domain registrar, add **A record**:
  - Name: `@`
  - Value: your Lightsail static IP
- [x] Add **www A record** pointing to same IP
- [x] Wait 5–30 min for DNS to propagate
- [x] Verify: `nslookup zarlybigfood.my` should return your IP
- [x] Update `nginx.conf` with your real domain:
  ```nginx
  server_name zarlybigfood.my www.zarlybigfood.my;
  ```

---

### Phase 4 — VPS Initial Setup

SSH into your instance (run from your project root):
```bash
ssh -i secure_keys/zarlysshkey.pem ubuntu@52.220.39.92
```

> **Note:** The SSH key (`secure_keys/zarlysshkey.pem`) must be in OPENSSH format.
> If you get "Permission denied (publickey)", convert it first:
> ```bash
> ssh-keygen -p -N "" -f secure_keys/zarlysshkey.pem
> ```
> Then add the public key to the VPS via Lightsail browser SSH:
> ```bash
> echo "$(ssh-keygen -y -f secure_keys/zarlysshkey.pem)" >> ~/.ssh/authorized_keys
> ```

- [ ] Update system
  ```bash
  sudo apt update && sudo apt upgrade -y
  ```
- [ ] Install Docker
  ```bash
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh
  sudo usermod -aG docker ubuntu
  ```
- [ ] Install Docker Compose
  ```bash
  sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
  ```
- [ ] Log out and back in (for Docker permission changes to apply)
- [ ] Verify installation
  ```bash
  docker --version
  docker-compose --version
  ```

---

### Phase 5 — Upload the 3 Files to VPS

- [ ] Create deployment folder
  ```bash
  mkdir -p /home/ubuntu/zarlyhq
  cd /home/ubuntu/zarlyhq
  ```
- [ ] Upload `docker-compose.yml` from your PC (run from project root)
  ```bash
  scp -i secure_keys/lightsail.pem docker-compose.yml ubuntu@<ip>:/home/ubuntu/zarlyhq/
  ```
- [ ] Upload `nginx.conf` from your PC (run from project root)
  ```bash
  scp -i secure_keys/lightsail.pem nginx.conf ubuntu@<ip>:/home/ubuntu/zarlyhq/
  ```
- [ ] Create `.env` file on VPS
  ```bash
  nano /home/ubuntu/zarlyhq/.env
  ```
  Paste and fill in your values:
  ```env
  DEBUG=False
  SECRET_KEY=your-long-random-secret-key-here
  ALLOWED_HOSTS=zarlybigfood.my,www.zarlybigfood.my

  DB_NAME=zarlyos
  DB_USER=postgres
  DB_PASSWORD=your-strong-db-password

  STRIPE_SECRET_KEY=sk_test_YOUR_KEY
  STRIPE_PUBLISHABLE_KEY=pk_test_YOUR_KEY
  STRIPE_WEBHOOK_SECRET=whsec_YOUR_KEY

  FERNET_KEY=your-fernet-key-here

  EMAIL_HOST_USER=your-email@gmail.com
  EMAIL_HOST_PASSWORD=your-gmail-app-password
  ```

---

### Phase 6 — SSL Certificate (Let's Encrypt via Certbot)

> **What this does:** Issues a free 90-day TLS certificate from Let's Encrypt.
> Certbot verifies you own the domain by placing a file at `/.well-known/acme-challenge/`
> and having Let's Encrypt fetch it over HTTP. nginx must be running and serving that path.

- [x] Install Certbot on VPS
  ```bash
  sudo apt install certbot -y
  ```
- [x] Create webroot folder (where certbot places challenge files)
  ```bash
  sudo mkdir -p /var/www/certbot
  ```
- [x] Deploy HTTP-only `nginx.conf` first (no SSL block) so nginx stays up during challenge
  ```bash
  scp -i secure_keys/zarlysshkey.pem nginx.conf ubuntu@52.220.39.92:~/zarlyhq/nginx.conf
  docker compose restart nginx
  ```
- [x] Generate SSL certificate
  ```bash
  sudo certbot certonly --webroot -w /var/www/certbot \
    -d zarlybigfood.my -d www.zarlybigfood.my
  ```
  Certs are saved to `/etc/letsencrypt/live/zarlybigfood.my/`
- [x] Upload final HTTPS `nginx.conf` (with real cert paths + HTTP→HTTPS redirect)
  ```bash
  scp -i secure_keys/zarlysshkey.pem nginx.conf ubuntu@52.220.39.92:~/zarlyhq/nginx.conf
  docker compose restart nginx
  ```
- [ ] Set up auto-renewal (certs expire every 90 days)
  ```bash
  sudo crontab -e
  # Add this line:
  0 3 * * * certbot renew --quiet && docker compose -f /home/ubuntu/zarlyhq/docker-compose.yml restart nginx
  ```

---

### Phase 7 — Launch

- [ ] Pull image and start all containers
  ```bash
  cd /home/ubuntu/zarlyhq
  docker-compose up -d
  ```
- [ ] Verify all 3 containers are running
  ```bash
  docker-compose ps
  ```
- [ ] Run database migrations
  ```bash
  docker-compose exec django python manage.py migrate
  ```
- [ ] Create superuser (admin account)
  ```bash
  docker-compose exec django python manage.py createsuperuser
  ```
- [ ] Test site loads at `https://zarlybigfood.my`
- [ ] Test Stripe checkout with card `4242 4242 4242 4242` (any future date, any CVC)
- [ ] Check logs if anything looks wrong
  ```bash
  docker-compose logs -f
  ```

---

### Phase 8 — Stripe Live Mode (Do Anytime, Takes 1–7 Days)

You can deploy with test keys first and switch after approval.

**Apply (5 min):**
- [ ] Stripe Dashboard → complete account activation
- [ ] Submit: MyKad + personal bank account + address
- [ ] Business type: Sole Proprietor (no SSM needed to start)
- [ ] Wait 1–7 days for approval email

**After approval:**
- [ ] Get live keys: Stripe Dashboard → Developers → API Keys
- [ ] Update `.env` on VPS
  ```bash
  nano /home/ubuntu/zarlyhq/.env
  # Change sk_test_ → sk_live_
  # Change pk_test_ → pk_live_
  ```
- [ ] Restart Django
  ```bash
  docker-compose restart django
  ```

---

## Updating the App After Go-Live

Every time you push new code:

```bash
# On your PC — rebuild and push new image
docker build -t udieefr/zarlyhq:latest .
docker push udieefr/zarlyhq:latest

# On VPS — pull and restart
cd /home/ubuntu/zarlyhq
docker-compose pull django
docker-compose up -d
docker-compose exec django python manage.py migrate  # only if DB schema changed
```

---

## Useful Commands

```bash
# Live logs
docker-compose logs -f django

# Restart a service
docker-compose restart django
docker-compose restart nginx

# Resource usage
docker stats

# Database backup
docker-compose exec db pg_dump -U postgres zarlyos > backup_$(date +%Y%m%d).sql

# Test SSL renewal
sudo certbot renew --dry-run
```

---

## Costs

| Item | Cost |
|---|---|
| Lightsail 2GB | $12/month |
| Domain `.my` | ~RM 50/year |
| SSL (Let's Encrypt) | Free |
| Stripe fees | 2.9% + 30¢ per transaction |
| **Total fixed** | **~$13/month** |
