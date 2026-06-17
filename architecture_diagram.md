# ZarlyOS — Poster Architecture Diagram

Copy the ` ```mermaid ` block below into [mermaid.live](https://mermaid.live) or your AI agent.

```mermaid
graph LR
    classDef flow fill:#1a1a2e,color:#e0e0e0,stroke:#16213e,stroke-width:2px,rx:8,ry:8
    classDef secure fill:#0f3460,color:#e0e0e0,stroke:#16213e,stroke-width:2px,rx:8,ry:8
    classDef signature fill:#533483,color:#e0e0e0,stroke:#3b2573,stroke-width:2px,rx:8,ry:8
    classDef stack fill:#1a3a1a,color:#a0d0a0,stroke:#2a4a2a,stroke-width:2px,rx:8,ry:8

    subgraph TOP["Secure Order Flow"]
        direction LR

        F1["Fill order"]:::flow
        F2["SHA-256 hash"]:::flow
        F3["OTP to email"]:::flow
        F4["Confirm OTP"]:::secure
        F5["Order locked"]:::secure

        F6["Admin approves"]:::flow
        F7["Generate PDF"]:::flow
        F8["PyHanko PKCS#7 sign"]:::signature
        F9["Signed PDF stored"]:::signature
        F10["Verify via UUID"]:::signature

        F1 --> F2 --> F3 --> F4 --> F5
        F5 --> F6 --> F7 --> F8 --> F9 --> F10
    end

    subgraph BOTTOM["Tech Stack"]
        direction LR
        B1["Bootstrap 5"]:::stack
        B2["Django + Nginx (Docker)"]:::stack
        B3["PostgreSQL + Redis"]:::stack
        B1 --> B2 --> B3
    end

    F4 -.->|OTP cache| B3
    F7 -.->|ReportLab + pyHanko| B2
```

> **Color legend:** Dark boxes = user actions · Blue boxes = security anchors · Purple boxes = cryptographic integrity · Green boxes = infrastructure

---

## What to tweak for your poster

| Thing | How |
|-------|-----|
| **Colors** | Replace the hex values in `classDef` to match your poster palette |
| **Icons** | Swap the emoji for your own icons if rendering in Figma/Illustrator |
| **Labels** | Each box is `"icon<br/>Title<br/>subtitle"` — keep under 5 words |
| **Stack detail** | Add Nginx, Stripe, or Docker labels to the bottom tier if you want more detail |
| **Font** | mermaid.live supports `%%{init: {'themeVariables': { 'fontFamily': '...' }}}%%` at the top |

---

## Even simpler (if space is tight)

```mermaid
graph LR
    classDef A fill:#1a1a2e,color:#fff,stroke:#333
    classDef B fill:#0f3460,color:#fff,stroke:#333
    classDef C fill:#533483,color:#fff,stroke:#333

    subgraph "Secure Order Flow"
        direction LR
        S1["Fill Order"]:::A --> S2["SHA-256 Hash"]:::A --> S3["OTP Verify"]:::B --> S4["Locked"]:::B --> S5["Approve"]:::A --> S6["PDF"]:::A --> S7["PKCS#7 Sign"]:::C --> S8["Verify"]:::C
    end

    subgraph "Stack"
        direction LR
        T1["Bootstrap 5"]:::A --> T2["Django + Nginx"]:::A --> T3["PostgreSQL + Redis"]:::A
    end

    S4 -.->|cache| T3
    S7 -.->|ReportLab| T2
```
