#!/usr/bin/env python3
"""Generate a PPTX presentation from scratch using only stdlib (zipfile + xml).
PPTX = ZIP of Office Open XML files."""

import zipfile
import io
import os
from xml.etree.ElementTree import Element, SubElement, tostring

OUTPUT = "/home/ubuntu/zarlytemp/ZarlyOS_FYP_Poster.pptx"

# ── XML namespaces ──────────────────────────────────
NSMAP = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _el(tag, attrib=None, text=None, **extra):
    """Create an Element with the right namespace."""
    if ":" in tag:
        ns, local = tag.split(":", 1)
        uri = NSMAP.get(ns, "")
        e = Element(f"{{{uri}}}{local}", attrib=attrib or {}, **extra)
    else:
        e = Element(tag, attrib=attrib or {}, **extra)
    if text is not None:
        e.text = text
    return e


def _sub(parent, tag, attrib=None, text=None, **extra):
    e = _el(tag, attrib, text, **extra)
    parent.append(e)
    return e


def _pp(tag, attrib=None, text=None, **extra):
    return _el(f"p:{tag}", attrib, text, **extra)


def _a(tag, attrib=None, text=None, **extra):
    return _el(f"a:{tag}", attrib, text, **extra)


def _r(tag, attrib=None, text=None, **extra):
    return _el(f"r:{tag}", attrib, text, **extra)


def make_text_run(text, bold=False, size=1800, color="333333", font="Calibri"):
    """Create a <p:r> run element with text."""
    r = _pp("r")
    rPr = _sub(r, "p:rPr", {"lang": "en-US", "b": "1" if bold else "0", "sz": str(size)})
    _sub(rPr, "a:solidFill").append(_el("a:srgbClr", {"val": color}))
    _sub(rPr, "a:latin", {"typeface": font})
    _sub(r, "a:t").text = text
    r.append(_pp("endParaRPr"))
    return r


def make_paragraph(text, bold=False, size=1800, color="333333", font="Calibri", align="l"):
    """Create a <p:p> paragraph with one run."""
    p = _pp("p")
    if align != "l":
        _sub(p, "p:pPr", {"algn": align})
    p.append(make_text_run(text, bold=bold, size=size, color=color, font=font))
    return p


def make_text_body(paragraphs):
    """Create <p:txBody> from a list of paragraphs."""
    txBody = _pp("txBody")
    bodyPr = _sub(txBody, "a:bodyPr", {"wrap": "square", "rtlCol": "0"})
    _sub(txBody, "a:lstStyle")
    for p in paragraphs:
        txBody.append(p)
    return txBody


def make_shape(x, y, cx, cy, paragraphs, shape_id):
    """Create a <p:sp> shape with text."""
    A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
    P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

    sp = Element(f"{{{P_NS}}}sp")

    # nvSpPr
    nvSpPr = SubElement(sp, f"{{{P_NS}}}nvSpPr")
    SubElement(nvSpPr, f"{{{P_NS}}}cNvPr", {"id": str(shape_id), "name": f"TextBox {shape_id}"})
    SubElement(nvSpPr, f"{{{P_NS}}}cNvSpPr", {"txBox": "1"})
    SubElement(nvSpPr, f"{{{P_NS}}}nvPr")

    # spPr
    spPr = SubElement(sp, f"{{{P_NS}}}spPr")
    xfrm = SubElement(spPr, f"{{{A_NS}}}xfrm")
    SubElement(xfrm, f"{{{A_NS}}}off", {"x": str(x), "y": str(y)})
    SubElement(xfrm, f"{{{A_NS}}}ext", {"cx": str(cx), "cy": str(cy)})
    SubElement(spPr, f"{{{A_NS}}}prstGeom", {"prst": "rect"})

    # txBody
    txBody = SubElement(sp, f"{{{P_NS}}}txBody")
    SubElement(txBody, f"{{{A_NS}}}bodyPr", {"wrap": "square", "rtlCol": "0"})
    SubElement(txBody, f"{{{A_NS}}}lstStyle")
    for p in paragraphs:
        txBody.append(p)

    return sp


def build_slide_xml(title_text, content_paragraphs, title_color="FF9933", bg_color="0F172A"):
    """Build a complete slide XML."""
    root = Element(f"{{{NSMAP['p']}}}sld")
    root.set("xmlns:a", NSMAP["a"])
    root.set("xmlns:r", NSMAP["r"])
    root.set("xmlns:p", NSMAP["p"])

    cSld = _sub(root, "p:cSld")

    # Background
    bg = _sub(cSld, "p:bg")
    bgPr = _sub(bg, "p:bgPr")
    solidFill = _sub(bgPr, "a:solidFill")
    _sub(solidFill, "a:srgbClr", {"val": bg_color})

    # Slide dimensions (standard 16:9 = 12192000 x 6858000 EMU)
    root.set("p:sld", "")

    # Title shape
    if title_text:
        shapes = [
            make_shape(457200, 274320, 11430000, 800000,
                       [make_paragraph(title_text, bold=True, size=3600, color=title_color, font="Calibri", align="l")],
                       1),
        ]
    else:
        shapes = []

    # Content shapes
    y_pos = 1300000
    for para in content_paragraphs:
        # Estimate height based on text length
        text_len = len(para.get("text", ""))
        lines = max(1, text_len // 100 + 1)
        shape_h = lines * 350000 + 100000
        shapes.append(make_shape(
            457200, y_pos, 11430000, shape_h,
            [make_paragraph(para["text"], bold=para.get("bold", False),
                            size=para.get("size", 1600), color=para.get("color", "CCCCCC"),
                            font="Calibri", align=para.get("align", "l"))],
            len(shapes) + 1
        ))
        y_pos += shape_h + 100000

    for s in shapes:
        cSld.append(s)

    # Slide layout reference
    root.set("p:show", "")

    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + tostring(root, encoding="unicode")


# ── Slide Content ───────────────────────────────────

slides_data = [
    # ── SLIDE 0: TITLE ──
    {
        "title": "Secure Signature-Based Online Ordering System\nfor Zarly BigFood Sdn Bhd",
        "title_color": "FF9933",
        "bg": "0F172A",
        "content": [
            {"text": "", "size": 800, "color": "CCCCCC"},
            {"text": "Rusdi Bin Abd Rashid  |  AI230025", "bold": True, "size": 2400, "color": "FFFFFF"},
            {"text": "Supervisor: Dr Sofia Najwa Binti Ramli", "size": 1800, "color": "AAAAAA"},
            {"text": "Universiti Tun Hussein Onn Malaysia (UTHM)", "size": 1600, "color": "AAAAAA"},
            {"text": "Final Year Project (Cybersecurity)  |  Academic Year 2025/2026", "size": 1400, "color": "888888"},
            {"text": "", "size": 800},
            {"text": "Live at: zarlybigfood.my", "size": 1600, "color": "FF9933", "bold": True},
        ],
    },
    # ── SLIDE 1: DESCRIPTION ──
    {
        "title": "1. Description",
        "title_color": "FF9933",
        "bg": "0F172A",
        "content": [
            {"text": "What is ZarlyOS?", "bold": True, "size": 2400, "color": "FFFFFF"},
            {"text": "", "size": 600},
            {"text": "A secure, signature-based online ordering platform that replaces informal order intake methods "
                     "(WhatsApp, Instagram DMs, verbal agreements) with a centralized, tamper-proof digital system "
                     "for Zarly BigFood Sdn Bhd, a Malaysian F&B business.", "size": 1600, "color": "CCCCCC"},
            {"text": "", "size": 600},
            {"text": "How it secures every order:", "bold": True, "size": 2000, "color": "FFFFFF"},
            {"text": "", "size": 400},
            {"text": "1. Customer submits order  ->  SHA-256 commitment hash locks in the exact contents, identity, and timestamp",
             "size": 1500, "color": "CCCCCC"},
            {"text": "2. OTP confirmation via email  ->  Cryptographic 6-digit code (CSPRNG, 5-min TTL) proves customer intent",
             "size": 1500, "color": "CCCCCC"},
            {"text": "3. Admin approves  ->  PyHanko embeds PKCS#7 digital signature using company X.509 certificate",
             "size": 1500, "color": "CCCCCC"},
            {"text": "4. Customer can verify anytime  ->  Public UUID verification URL checks SHA-256 + PKCS#7 validity",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 600},
            {"text": "Non-repudiation goal: Neither the customer nor the company can deny a transaction after it is signed. "
                     "Grounded in ITU-T X.813 / RFC 2828, aligned with Malaysia's Electronic Commerce Act 2006 "
                     "and Digital Signature Act 1997.", "size": 1500, "color": "AAAAAA"},
            {"text": "", "size": 400},
            {"text": "Stack: Django 5.1  |  PostgreSQL 17  |  Redis 7  |  Nginx  |  Docker  |  Bootstrap 5",
             "size": 1400, "color": "FF9933", "bold": True},
        ],
    },
    # ── SLIDE 2: NOVELTY ──
    {
        "title": "2. Novelty",
        "title_color": "FF9933",
        "bg": "0F172A",
        "content": [
            {"text": "What makes this different from a typical food ordering system?", "bold": True, "size": 2000, "color": "FFFFFF"},
            {"text": "", "size": 600},
            {"text": "Two-Party Non-Repudiation (NRO + NRF)", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "Customer side: OTP-confirmed SHA-256 commitment hash (Non-Repudiation of Origin). "
                     "Company side: PyHanko PKCS#7 digital signature on approved PDF (Non-Repudiation of Finalization). "
                     "A formal security architecture rarely found in food ordering platforms.", "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Public Cryptographic Receipt Verification", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "Any recipient of a signed receipt can verify authenticity at a public URL (/verify/<uuid>) "
                     "without logging in. The system recomputes SHA-256, validates PKCS#7, and displays the full "
                     "non-repudiation record.", "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Hash-Chained Immutable Audit Trail", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "Every admin action is recorded with chain_hash = SHA-256(previous | actor | action | target | metadata | ip). "
                     "verify_chain() method detects any tampering across 30+ action types. Genesis: SHA-256(\"ZARLY_AUDIT_CHAIN_V1\").",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Live Tamper Detection on Receipt Download", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "Every receipt download recomputes the file SHA-256. Match = green \"PAID & SIGNED\" watermark. "
                     "Mismatch = red \"VOID\" stamp. Original file on disk is never modified.",
             "size": 1500, "color": "CCCCCC"},
        ],
    },
    # ── SLIDE 3: SOCIETAL BENEFITS ──
    {
        "title": "3. Societal Benefits",
        "title_color": "FF9933",
        "bg": "0F172A",
        "content": [
            {"text": "Real-world impact for Malaysian SMEs and F&B businesses", "bold": True, "size": 2000, "color": "FFFFFF"},
            {"text": "", "size": 600},
            {"text": "Replaces legally weak informal order intake", "bold": True, "size": 2000, "color": "FF9933"},
            {"text": "WhatsApp messages, Instagram DMs, and verbal agreements provide zero auditable proof. "
                     "ZarlyOS replaces all of them with one platform where every order carries cryptographic evidence "
                     "of both customer intent and company acceptance.",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Legal proof for dispute resolution", "bold": True, "size": 2000, "color": "FF9933"},
            {"text": "If a customer disputes an order, the commitment hash proves exact contents they OTP-confirmed. "
                     "The PKCS#7-signed PDF proves the company approved those contents. Both are independently "
                     "verifiable without database access.",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Enterprise-grade security at SME budget", "bold": True, "size": 2000, "color": "FF9933"},
            {"text": "Runs on ~$13/month AWS Lightsail VPS with Docker Compose. Brings cryptographic integrity to "
                     "small food businesses that cannot afford commercial e-signature solutions.",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Protects both parties equally", "bold": True, "size": 2000, "color": "FF9933"},
            {"text": "Unlike standard e-commerce where the platform holds all evidence, customers get their own verifiable "
                     "receipt (signed PDF + public UUID verification URL). Neither party depends on the other to prove "
                     "what happened.", "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Supports Malaysian payment infrastructure", "bold": True, "size": 2000, "color": "FF9933"},
            {"text": "Integrates Stripe (international cards) alongside DuitNow QR and bank transfer with manual proof "
                     "upload — practical for the local Malaysian F&B market.",
             "size": 1500, "color": "CCCCCC"},
        ],
    },
    # ── SLIDE 4: UNIQUENESS ──
    {
        "title": "4. Uniqueness",
        "title_color": "FF9933",
        "bg": "0F172A",
        "content": [
            {"text": "Specific technical implementations unique to this system", "bold": True, "size": 2000, "color": "FFFFFF"},
            {"text": "", "size": 600},
            {"text": "Dual-Mechanism Non-Repudiation Architecture", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "Customer: OTP + SHA-256 commitment hash (consumers lack PKI). Company: PyHanko PKCS#7 + X.509. "
                     "Deliberate architectural choice grounded in ITU-T X.813. Design spec maps NRO and NRF to "
                     "different evidence types and covers all four dispute scenarios.",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Blockchain-Style Hash-Chained Audit Log", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "AuditLog model with SHA-256 chain across 30+ action types. Single verify_chain() call validates "
                     "entire history. Row-level race-condition protection via select_for_update() + transaction.atomic().",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Private Media Serving via X-Accel-Redirect", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "Sensitive files (payment proofs, signed PDFs, complaint evidence) blocked at Nginx level (deny all) "
                     "and served exclusively through Django's authenticated /files/<path> endpoint. Nginx internal "
                     "X-Accel-Redirect handles zero-copy streaming after Django authorizes ownership.",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Fernet-Encrypted Support Chat at Rest", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "SupportMessage bodies stored as Fernet ciphertext (AES-128-CBC + HMAC-SHA256). Encrypted on write, "
                     "decrypted on read. Tampered ciphertext detected and displayed as [encrypted]. delete() raises "
                     "PermissionError — messages are immutable for non-repudiation of support communications.",
             "size": 1500, "color": "CCCCCC"},
        ],
    },
    # ── SLIDE 5: STATUS OF PRODUCT ──
    {
        "title": "5. Status of Product",
        "title_color": "FF9933",
        "bg": "0F172A",
        "content": [
            {"text": "Current deployment and testing status", "bold": True, "size": 2000, "color": "FFFFFF"},
            {"text": "", "size": 600},
            {"text": "LIVE at zarlybigfood.my", "bold": True, "size": 2800, "color": "FF9933"},
            {"text": "", "size": 400},
            {"text": "Deployment: AWS Lightsail VPS (Ubuntu 24.04, $12/month) with Docker Compose — "
                     "4 containers: Nginx (SSL via Let's Encrypt, TLS 1.2/1.3, HSTS), Django 5.1 + Gunicorn, "
                     "PostgreSQL 17, Redis 7.",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "Security hardening: CSP with per-request nonces, private media blocking at reverse-proxy level, "
                     "rate limiting (10 req/s general, 30 req/m API), CSRF protection, session timeout (1-hour inactivity), "
                     "step-up authentication (sudo) for sensitive manager actions.",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "User Acceptance Testing: 26 participants (18 customers, 8 staff)", "bold": True, "size": 1800, "color": "FFFFFF"},
            {"text": "", "size": 400},
            {"text": "Test Suite: 262+ pytest-django tests across 14 test files", "bold": True, "size": 1800, "color": "FFFFFF"},
            {"text": "Dedicated test classes: Non-repudiation (21 tests), Security fixes (26 tests), CSP (13 tests), "
                     "Stock race conditions (12 tests), Support chat encryption (25 tests), Functional (31 tests), "
                     "Registration (25 tests), Delivery (15 tests), Database performance (32 tests).",
             "size": 1400, "color": "AAAAAA"},
        ],
    },
    # ── SLIDE 6: ARCHITECTURE FLOW ──
    {
        "title": "6. System Architecture Flow",
        "title_color": "FF9933",
        "bg": "0F172A",
        "content": [
            {"text": "Secure order lifecycle — from cart to cryptographically signed receipt", "bold": True, "size": 2000, "color": "FFFFFF"},
            {"text": "", "size": 600},
            {"text": "1.  Customer fills order  ->  2.  Order submitted, stock locked (SELECT FOR UPDATE)", "size": 1500, "color": "CCCCCC"},
            {"text": "3.  SHA-256 commitment hash computed  ->  4.  OTP sent to email (6-digit CSPRNG, 5-min TTL)", "size": 1500, "color": "CCCCCC"},
            {"text": "5.  Customer confirms OTP  ->  6.  Sales Admin reviews and verifies payment", "size": 1500, "color": "CCCCCC"},
            {"text": "7.  Admin approves, PDF generated (ReportLab + integrity hash)  ->  8.  PyHanko signs PDF (PKCS#7, X.509)", "size": 1500, "color": "CCCCCC"},
            {"text": "9.  Signed PDF stored, UUID verification token issued  ->  10.  Customer verifies receipt via public URL", "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 800},
            {"text": "Tech Stack:  Browser (Bootstrap 5)  ->  Django + Nginx (Docker)  ->  PostgreSQL + Redis", "size": 1800, "color": "FF9933", "bold": True},
        ],
    },
    # ── SLIDE 7: SCREENSHOTS ──
    {
        "title": "7. Key Screenshots (Recommended)",
        "title_color": "FF9933",
        "bg": "0F172A",
        "content": [
            {"text": "Three most visually impressive pages for the poster", "bold": True, "size": 2000, "color": "FFFFFF"},
            {"text": "", "size": 600},
            {"text": "1. Receipt Verification Page (/verify/<uuid>)", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "Color-coded pass/fail banners (green Valid / red Tampered), SHA-256 hash display, PKCS#7 signature "
                     "validation results, certificate details, and full Non-Repudiation Record. This single page "
                     "communicates the entire security contribution at a glance.",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "2. Landing Page (/start/)", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "Dark navy/orange split hero with serif headline, 4-column feature strip in burnt orange, "
                     "best-sellers grid, strong brand expression. Shows the system is production-grade and "
                     "customer-facing — not just a backend tool.",
             "size": 1500, "color": "CCCCCC"},
            {"text": "", "size": 400},
            {"text": "3. Sales Admin Dashboard (/dashboard/)", "bold": True, "size": 2200, "color": "FF9933"},
            {"text": "Dark metric strip with large orange numbers (Pending, Awaiting Payment, Approved, Rejected), "
                     "structured order tables with status pills, payment proof hover previews. Demonstrates a real "
                     "operational tool — not a prototype.",
             "size": 1500, "color": "CCCCCC"},
        ],
    },
]


# ── Build PPTX ──────────────────────────────────────

def build_pptx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

        # ── [Content_Types].xml ──
        ct = Element(f"{{{CONTENT_TYPES_NS}}}Types")
        ct.set("xmlns", CONTENT_TYPES_NS)
        for ext in ["rels", "xml"]:
            SubElement(ct, "Default", {"Extension": ext,
                       "ContentType": "application/vnd.openxmlformats-package.relationships+xml"
                       if ext == "rels" else "application/xml"})
        for part, ctype in [
            ("/ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"),
            ("/ppt/slideMasters/slideMaster1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"),
            ("/ppt/slideLayouts/slideLayout1.xml", "application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"),
            ("/ppt/theme/theme1.xml", "application/vnd.openxmlformats-officedocument.theme+xml"),
        ]:
            SubElement(ct, "Override", {"PartName": part, "ContentType": ctype})
        for i in range(len(slides_data)):
            SubElement(ct, "Override", {
                "PartName": f"/ppt/slides/slide{i+1}.xml",
                "ContentType": "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
            })
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
                    tostring(ct, encoding="unicode"))

        # ── _rels/.rels ──
        rels_root = Element(f"{{{RELS_NS}}}Relationships")
        rels_root.set("xmlns", RELS_NS)
        SubElement(rels_root, "Relationship", {"Id": "rId1", "Type":
                   "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
                   "Target": "ppt/presentation.xml"})
        zf.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
                    tostring(rels_root, encoding="unicode"))

        # ── ppt/_rels/presentation.xml.rels ──
        prels = Element(f"{{{RELS_NS}}}Relationships")
        prels.set("xmlns", RELS_NS)
        SubElement(prels, "Relationship", {"Id": "rId1", "Type":
                   "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster",
                   "Target": "slideMasters/slideMaster1.xml"})
        SubElement(prels, "Relationship", {"Id": "rId2", "Type":
                   "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
                   "Target": "theme/theme1.xml"})
        for i in range(len(slides_data)):
            SubElement(prels, "Relationship", {
                "Id": f"rId{10+i}", "Type":
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide",
                "Target": f"slides/slide{i+1}.xml",
            })
        zf.writestr("ppt/_rels/presentation.xml.rels",
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
                    tostring(prels, encoding="unicode"))

        # ── ppt/presentation.xml ──
        pres = Element(f"{{{NSMAP['p']}}}presentation")
        pres.set("xmlns:a", NSMAP["a"])
        pres.set("xmlns:r", NSMAP["r"])
        pres.set("xmlns:p", NSMAP["p"])
        sml = _sub(pres, "p:sldMasterIdLst")
        _sub(sml, "p:sldMasterId", {"id": "2147483648", "r:id": "rId1"})
        sldIdLst = _sub(pres, "p:sldIdLst")
        for i in range(len(slides_data)):
            _sub(sldIdLst, "p:sldId", {"id": str(256 + i), "r:id": f"rId{10+i}"})
        _sub(pres, "p:sldSz", {"cx": "12192000", "cy": "6858000"})
        _sub(pres, "p:notesSz", {"cx": "6858000", "cy": "9144000"})
        zf.writestr("ppt/presentation.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
                    tostring(pres, encoding="unicode"))

        # ── ppt/slideMasters/slideMaster1.xml ──
        sm = Element(f"{{{NSMAP['p']}}}sldMaster")
        sm.set("xmlns:a", NSMAP["a"])
        sm.set("xmlns:r", NSMAP["r"])
        sm.set("xmlns:p", NSMAP["p"])
        _sub(sm, "p:cSld").append(_sub(_el("p:bg"), "p:bgRef", {"idx": "1001"}))
        sldLayoutIdLst = _sub(sm, "p:sldLayoutIdLst")
        _sub(sldLayoutIdLst, "p:sldLayoutId", {"id": "2147483649", "r:id": "rId1"})
        zf.writestr("ppt/slideMasters/slideMaster1.xml",
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
                    tostring(sm, encoding="unicode"))

        # ── ppt/slideMasters/_rels/slideMaster1.xml.rels ──
        smrels = Element(f"{{{RELS_NS}}}Relationships")
        smrels.set("xmlns", RELS_NS)
        SubElement(smrels, "Relationship", {"Id": "rId1", "Type":
                   "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout",
                   "Target": "../slideLayouts/slideLayout1.xml"})
        zf.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels",
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
                    tostring(smrels, encoding="unicode"))

        # ── ppt/slideLayouts/slideLayout1.xml ──
        sl = Element(f"{{{NSMAP['p']}}}sldLayout")
        sl.set("xmlns:a", NSMAP["a"])
        sl.set("xmlns:r", NSMAP["r"])
        sl.set("xmlns:p", NSMAP["p"])
        sl.set("type", "blank")
        _sub(sl, "p:cSld", {"name": "Blank"})
        zf.writestr("ppt/slideLayouts/slideLayout1.xml",
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
                    tostring(sl, encoding="unicode"))

        # ── ppt/theme/theme1.xml (minimal dark theme) ──
        theme = Element(f"{{{NSMAP['a']}}}theme")
        theme.set("xmlns:a", NSMAP["a"])
        theme.set("name", "Zarly Dark")
        themeElements = _sub(theme, "a:themeElements")
        clrScheme = _sub(themeElements, "a:clrScheme", {"name": "Zarly"})
        colors = [("dk1", "000000"), ("lt1", "FFFFFF"), ("dk2", "0F172A"), ("lt2", "FF9933"),
                  ("accent1", "FF9933"), ("accent2", "10B981"), ("accent3", "EF4444"),
                  ("accent4", "0EA5E9"), ("accent5", "F59E0B"), ("accent6", "533483"),
                  ("hlink", "FF9933"), ("folHlink", "CC7722")]
        for name, val in colors:
            _sub(clrScheme, f"a:{name}").append(_el("a:srgbClr", {"val": val}))
        _sub(themeElements, "a:fontScheme", {"name": "Zarly"}).append(
            _sub(_el("a:majorFont"), "a:latin", {"typeface": "Calibri"})
        )
        themeElements.find("{http://schemas.openxmlformats.org/drawingml/2006/main}fontScheme").append(
            _sub(_el("a:minorFont"), "a:latin", {"typeface": "Calibri"})
        )
        _sub(themeElements, "a:fmtScheme", {"name": "Zarly"})

        zf.writestr("ppt/theme/theme1.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
                    tostring(theme, encoding="unicode"))

        # ── Slides ──
        for i, sdata in enumerate(slides_data):
            xml = build_slide_xml(sdata["title"], sdata["content"],
                                  title_color=sdata.get("title_color", "FF9933"),
                                  bg_color=sdata.get("bg", "0F172A"))
            zf.writestr(f"ppt/slides/slide{i+1}.xml", xml)

            # Slide rels
            sr = Element(f"{{{RELS_NS}}}Relationships")
            sr.set("xmlns", RELS_NS)
            SubElement(sr, "Relationship", {"Id": "rId1", "Type":
                       "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout",
                       "Target": "../slideLayouts/slideLayout1.xml"})
            zf.writestr(f"ppt/slides/_rels/slide{i+1}.xml.rels",
                        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
                        tostring(sr, encoding="unicode"))

    return buf.getvalue()


if __name__ == "__main__":
    pptx_bytes = build_pptx()
    with open(OUTPUT, "wb") as f:
        f.write(pptx_bytes)
    print(f"PPTX generated: {OUTPUT}")
    print(f"Size: {len(pptx_bytes):,} bytes")
    print(f"Slides: {len(slides_data)}")
