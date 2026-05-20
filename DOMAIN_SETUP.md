# Domain Setup Guide

## Step 1: Choose & Buy a Domain

Popular registrars:
- **Namecheap**: Cheap, good support (~$8-12/year)
- **GoDaddy**: Popular, many extensions (~$10-15/year)
- **Google Domains**: Clean interface, integrated with Google (~$12-15/year)
- **Route 53**: AWS native, integrates with Lightsail (varies)
- **Local registrars**: Check for .com.my domains (Hostmaster Malaysia)

**Recommended**: Namecheap or Route 53 for ease

---

## Step 2: Get Your Lightsail Static IP

1. Launch Lightsail instance (see DEPLOYMENT.md)
2. Go to **Networking** → **Create static IP**
3. Copy the IP address (e.g., `203.192.123.45`)

---

## Step 3: Point Domain to Lightsail

### For Namecheap:
1. Log in to Namecheap
2. Go to **Domain List**
3. Click **Manage** next to your domain
4. Go to **Advanced DNS**
5. Find the **A Record** for `@` (root domain)
   - **Name**: `@`
   - **Type**: `A`
   - **Value**: Your Lightsail static IP
   - **TTL**: `Auto` or `3600`
6. Click **Save Changes**

### For GoDaddy:
1. Log in to GoDaddy
2. Go to **My Products** → **Domains**
3. Click your domain
4. Go to **DNS**
5. Edit the **A** record:
   - **Name**: `@`
   - **Data**: Your Lightsail static IP
6. Click **Save**

### For Google Domains:
1. Log in to Google Domains
2. Select your domain
3. Go to **DNS**
4. Scroll to **Custom records**
5. Add **A record**:
   - **Name**: `@`
   - **Type**: `A`
   - **TTL**: `3600`
   - **Data**: Your Lightsail static IP
6. Click **Create**

### For Route 53 (AWS):
1. Go to **Route 53** in AWS Console
2. Click **Hosted zones**
3. Create or select your domain
4. Create **A record**:
   - **Name**: `@` (or leave blank for root)
   - **Type**: `A`
   - **Value**: Your Lightsail static IP
   - **TTL**: `300`
5. Click **Create record**

---

## Step 4: Add www Subdomain (Optional)

Repeat the above but create a second **A record**:
- **Name**: `www`
- **Type**: `A`
- **Value**: Your Lightsail static IP

---

## Step 5: Wait for DNS Propagation

DNS changes take **5-30 minutes** to propagate globally.

### Check if DNS is ready:

```bash
# On your computer (terminal)
nslookup your-domain.com

# Should show your Lightsail IP
# Example output:
# Server:  8.8.8.8
# Address: 8.8.8.8#53
# Non-authoritative answer:
# Name: your-domain.com
# Address: 203.192.123.45
```

Or use online tools:
- https://www.nslookup.io/
- https://dnschecker.org/

---

## Step 6: Test Domain Access

Once DNS resolves:

```bash
# Ping your domain
ping your-domain.com

# Should show your Lightsail IP
# Example:
# PING your-domain.com (203.192.123.45) 56(84) bytes of data.
```

---

## Step 7: Update Nginx Configuration

Once domain is working, update `nginx.conf`:

Change:
```nginx
server_name localhost;
```

To:
```nginx
server_name your-domain.com www.your-domain.com;
```

And update SSL certificate paths:
```nginx
ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
```

---

## Step 8: Get SSL Certificate

Once DNS works and Nginx is updated:

```bash
# SSH into Lightsail
ssh -i ~/.ssh/lightsail.pem ubuntu@your-lightsail-ip

# Stop Nginx
sudo systemctl stop nginx

# Generate certificate with Certbot
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# Follow prompts:
# - Email: your-email@example.com
# - Accept terms: Y
# - Share email: N (optional)

# Start Nginx
sudo systemctl start nginx

# Verify certificate
sudo certbot certificates
```

---

## Troubleshooting

### Domain not resolving?
1. Check DNS record is set correctly in registrar
2. Wait a bit longer (DNS can take up to 30 mins)
3. Clear your local DNS cache:
   ```bash
   # Windows
   ipconfig /flushdns
   
   # Mac
   sudo dscacheutil -flushcache
   
   # Linux
   sudo systemd-resolve --flush-caches
   ```

### Certificate generation failed?
1. Ensure domain resolves to Lightsail IP
2. Ensure port 80 is open in firewall
3. Try again: `sudo certbot certonly --standalone -d your-domain.com`

### Nginx not starting after cert?
1. Check Nginx config syntax: `sudo nginx -t`
2. Check certificate paths exist: `sudo ls -la /etc/letsencrypt/live/your-domain.com/`
3. Reload Nginx: `sudo systemctl reload nginx`

---

## After Setup

1. Access your app: `https://your-domain.com`
2. Update ALLOWED_HOSTS in `.env.prod`
3. Restart Django container: `docker-compose restart django`
4. Test order flow with Stripe test card

