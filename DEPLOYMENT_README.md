# ZarlyHQ Deployment - Complete Package

This folder contains everything you need to deploy ZarlyHQ to AWS Lightsail with Docker, PostgreSQL, Nginx, and Let's Encrypt SSL.

## 🐳 What is Docker? (Quick Explainer)

Docker packages your entire application (code + dependencies) into a portable **container image**. When you:

1. **Build** on your PC: Creates `zarlyos:latest` image with everything inside
2. **Push** to registry: Store image (like GitHub for code)
3. **Pull** on VPS: Download the same image
4. **Run**: `docker-compose up -d` → App runs **exactly** as it ran on your PC

**The guarantee**: App behaves identically everywhere (no more "works on my machine" problems).

### Key Docker Concepts
- **Image** = Blueprint (like a recipe)
- **Container** = Running app (like a lightweight virtual computer)
- **Docker Compose** = Manages multiple containers (Django + PostgreSQL + Nginx)

**Full explanation**: See DEPLOYMENT.md → "Understanding Docker"

---

## 📋 Files Created

### Configuration Files
| File | Purpose |
|------|---------|
| **Dockerfile** | Docker image definition (Python 3.11, Gunicorn, auto-collect static files) |
| **.dockerignore** | Excludes unnecessary files from Docker image |
| **docker-compose.yml** | Orchestrates PostgreSQL, Django, and Nginx containers |
| **nginx.conf** | Nginx reverse proxy, SSL termination, rate limiting |
| **gunicorn_config.py** | Gunicorn WSGI server configuration (workers, timeouts) |
| **.env.prod.example** | Environment variables template for production |

### Documentation Files
| File | Purpose |
|------|---------|
| **DEPLOYMENT.md** | Complete step-by-step deployment guide (all phases) |
| **DOMAIN_SETUP.md** | How to buy domain and configure DNS records |
| **DEPLOYMENT_CHECKLIST.md** | Quick reference checklist during deployment |

### Updated Files
| File | Change |
|------|--------|
| **requirements.txt** | Added gunicorn==23.0.0 |
| **docker-compose.yml** | Rewritten for production with Django + Nginx services |

---

## 🚀 Quick Start

### 1. Prepare Files
All files are ready in the project root. No additional setup needed.

### 2. Buy Domain & VPS
- Buy domain (Namecheap, GoDaddy, etc.) → ~$10-15/year
- Launch Lightsail instance (Ubuntu 24.04, 2GB, $12/month)
- Allocate static IP and configure firewall

### 3. Deploy
```bash
# SSH into Lightsail
ssh -i ~/.ssh/lightsail.pem ubuntu@<your-ip>

# Clone repo
git clone https://github.com/your/repo.git
cd ZarlyHQ

# Create production environment
cp .env.prod.example .env.prod
# Edit .env.prod with:
# - SECRET_KEY (new random value)
# - ALLOWED_HOSTS (your domain)
# - Database password
# - Stripe test keys

# Build and deploy
docker-compose build
docker-compose run --rm django python manage.py migrate
docker-compose run --rm django python manage.py createsuperuser
docker-compose up -d

# Get SSL certificate
sudo certbot certonly --standalone -d your-domain.com
```

### 4. Test
- Visit `https://your-domain.com`
- Sign up as customer
- Create test order with Stripe card: `4242 4242 4242 4242`

---

## 📚 Full Documentation

| Guide | Read When |
|-------|-----------|
| **DEPLOYMENT.md** | Full walkthrough of all steps (start here) |
| **DOMAIN_SETUP.md** | Buying domain and setting up DNS records |
| **DEPLOYMENT_CHECKLIST.md** | Reference checklist during actual deployment |

---

## 🎯 Phase Overview

| Phase | Time | Task |
|-------|------|------|
| Setup | 5 min | Create Stripe account (apply for live) |
| 1 | 5 min | Launch Lightsail instance |
| 2 | 10 min | Install Docker, Nginx, Certbot |
| 3 | 5 min | Create Docker configuration files ✅ (already done) |
| 4 | 5 min | Create Nginx reverse proxy config ✅ (already done) |
| 5 | 2 min | Update Django settings |
| 6 | 10 min | Generate SSL certificate |
| 7 | 5 min | Run migrations, create superuser |
| 8 | 10 min | Deploy and test with test Stripe |
| **Background** | 1-7 days | Stripe reviews live account application |
| **After Approval** | 2 min | Swap test keys → live keys |
| **Total Active** | **52 min** | Full initial deployment |
| **Wait time** | 1-7 days | Stripe approval (doesn't block deployment) |

---

## 💡 Why This Timeline Works

1. **Deploy TODAY with test Stripe keys**
   - Full app working end-to-end
   - Test with test card: `4242 4242 4242 4242`
   - No real charges

2. **While you're testing, Stripe approves live account**
   - Takes 1-7 days in background
   - You're already using the app

3. **Switch to live keys when approved**
   - Just update `.env.prod`
   - Restart: `docker-compose restart django`
   - Start accepting real payments

---

## 🏗️ Architecture

```
Your Computer
    ↓ (SSH)
Lightsail VPS (Ubuntu 24.04, 2GB RAM)
    ├─ Nginx (Port 80/443)
    │   ├─ SSL termination
    │   ├─ Rate limiting
    │   └─ Static file serving
    │
    ├─ Django/Gunicorn (Port 8000)
    │   ├─ 4-8 workers
    │   ├─ 30s timeout
    │   └─ Auto-restart
    │
    └─ PostgreSQL (Port 5432)
        ├─ Persistent storage
        ├─ Backups
        └─ Statement timeout: 10s
```

---

## 🔒 Security Features Built-In

- **SSL/TLS**: Let's Encrypt (free, auto-renewing)
- **Reverse Proxy**: Nginx handles external requests
- **Rate Limiting**: Configured per endpoint (10-30 req/s)
- **HSTS**: Enforces HTTPS (31536000 seconds)
- **Security Headers**: X-Frame-Options, X-Content-Type-Options, CSP
- **Non-root User**: Django runs as unprivileged `appuser`
- **Database Isolation**: PostgreSQL only accessible internally
- **Statement Timeout**: 10s to prevent long-running queries
- **Gunicorn Timeout**: 30s to handle slow requests

---

## 📦 Cost Breakdown

| Component | Cost/Month | Notes |
|-----------|-----------|-------|
| Lightsail Instance | $12 | 2GB RAM, 1 vCPU, 60GB SSD |
| Static IP | Included | First 3 free on Lightsail |
| Domain | ~$10 | One-time yearly cost (~$1/month avg) |
| SSL Certificate | Free | Let's Encrypt auto-renews |
| **Total** | **~$22/month** | Scales to $20/month if you upgrade |

---

## ✅ Pre-Deployment Checklist

- [ ] All code committed
- [ ] No secrets in git (.env excluded)
- [ ] AWS account ready
- [ ] Domain registrar chosen
- [ ] Read DEPLOYMENT.md completely
- [ ] Prepared .env.prod values

---

## 🆘 Troubleshooting

### Common Issues

**Docker won't start?**
```bash
# Check logs
docker-compose logs

# Rebuild
docker-compose down
docker-compose build
docker-compose up -d
```

**Domain not resolving?**
```bash
# Test DNS
nslookup your-domain.com

# Check firewall
sudo ufw status
```

**SSL certificate errors?**
```bash
# Test renewal
sudo certbot renew --dry-run

# Force renew
sudo certbot renew --force-renewal
docker-compose restart nginx
```

See **DEPLOYMENT_CHECKLIST.md** for more troubleshooting.

---

## 📖 Next Steps

1. **Read DEPLOYMENT.md** - Complete guide with all steps
2. **Buy domain** - See DOMAIN_SETUP.md for detailed instructions
3. **Launch Lightsail** - Create VPS instance
4. **Deploy** - Follow DEPLOYMENT.md phases 1-8
5. **Monitor** - Check logs with `docker-compose logs -f`

---

## 🎯 Phase Overview

| Phase | Time | Task |
|-------|------|------|
| 1 | 5 min | Launch Lightsail instance |
| 2 | 10 min | Install Docker, Nginx, Certbot |
| 3 | 5 min | Create Docker configuration files |
| 4 | 5 min | Create Nginx reverse proxy config |
| 5 | 2 min | Update Django settings |
| 6 | 10 min | Generate SSL certificate |
| 7 | 5 min | Run migrations, create superuser |
| 8 | 10 min | Deploy and test |
| **Total** | **52 min** | Full deployment |

---

## 📞 Support & Questions

- **Deployment issues?** Check DEPLOYMENT_CHECKLIST.md
- **Domain not working?** See DOMAIN_SETUP.md
- **Docker help?** See Docker Compose logs: `docker-compose logs`
- **Nginx errors?** Check `docker-compose logs nginx`
- **Django errors?** Check `docker-compose logs django`

---

## 🔄 Updates & Maintenance

### Deploy Updates
```bash
git pull origin main
docker-compose build
docker-compose up -d
docker-compose run --rm django python manage.py migrate
```

### Backup Database
```bash
docker-compose exec db pg_dump -U postgres zarlyos > backup.sql
```

### Monitor Services
```bash
docker stats  # CPU, memory usage
docker-compose logs -f  # Live logs
```

---

**Happy deploying! 🚀**
