# AgenLang

**Shared contract substrate for secure, auditable, economically fair inter-agent communication**

AgenLang is a lightweight, model-agnostic standard that lets personal agents (OpenClaw/Amazo-style) and ZHC swarms safely delegate tasks to each other.

**Key features**
- 40–110 token overhead (compressed)
- Cryptographic capability proofs (prevents supply-chain attacks)
- Intent anchoring (prevents goal hijacking)
- Built-in JouleWork settlement
- GDPR-ready memory handoff and purge
- Full HMAC-protected Structured Execution Record (SER) with replay

**Installation**

```bash
pip install agenlang          # Python (recommended for most agents)
npm install agenlang          # JavaScript / TypeScript