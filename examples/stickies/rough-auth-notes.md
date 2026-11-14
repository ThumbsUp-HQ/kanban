# Rough Auth Notes & Ideas

- Need to support multi-card authentication for enterprise users
- Local admin account must have break-glass access
- References: #KAN-101 and #KAN-102 for OAuth provider mappings

```mermaid
sequenceDiagram
    autonumber
    actor User as User Browser
    participant App as Kanban Web
    participant Auth as Auth Service
    participant IdP as Identity Provider
    User->>App: Click Login with OIDC
    App->>Auth: Initiate OAuth Flow (PKCE S256)
    Auth->>IdP: Redirect to IdP Auth URL
    IdP-->>User: Present Login Challenge
    User->>IdP: Provide Credentials
    IdP-->>Auth: Callback with Authorization Code
    Auth->>IdP: Exchange Code + PKCE Verifier for Tokens
    IdP-->>Auth: ID Token + Access Token
    Auth->>App: Issue Session Cookie
    App-->>User: Render Dashboard
```

- Action item: implement WebAuthn Passkey registration
- Action item: configure TOTP backup generator
