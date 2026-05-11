# Research: LinuxDo OAuth 2.0 API Specification

- **Query**: LinuxDo OAuth 2.0 API specification details
- **Scope**: external
- **Date**: 2026-05-01

## Findings

### OAuth 2.0 Endpoints

| Endpoint | URL |
|---|---|
| Authorization | `https://connect.linux.do/oauth2/authorize` |
| Token | `https://connect.linux.do/oauth2/token` |
| User Info | `https://connect.linux.do/api/user` |

### Client Registration

**Registration URL**: https://connect.linux.do/

**Steps**:
1. Login with LinuxDo account at Connect.Linux.Do
2. Navigate to "我的应用接入" (My App Integrations)
3. Click "申请新接入" (Apply for New Access)
4. Fill in:
   - 应用名称 (App Name)
   - 应用描述 (Description)
   - 回调地址 (Redirect URI) - must match exactly
5. Submit to receive **Client ID** and **Client Secret**

**Note**: Self-service registration is now available (previously required contacting admin).

### Authorization Code Flow

**Step 1: Authorization Request**
```
GET https://connect.linux.do/oauth2/authorize?
  response_type=code&
  client_id=YOUR_CLIENT_ID&
  redirect_uri=YOUR_REDIRECT_URI&
  state=RANDOM_STRING&
  scope=user
```

**Step 2: Token Exchange**
```bash
curl -X POST https://connect.linux.do/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept: application/json" \
  -d "client_id=CLIENT_ID&client_secret=CLIENT_SECRET&code=AUTH_CODE&redirect_uri=REDIRECT_URI&grant_type=authorization_code"
```

**Step 3: Get User Info**
```bash
curl -X GET https://connect.linux.do/api/user \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

### Available Scopes

| Scope | Description |
|---|---|
| `user` | Default and most common scope for basic user info |
| `openid profile email` | Standard OIDC scopes (also supported) |
| `read` | Read access (less documented) |
| `write` | Write access (less documented) |

**Recommendation**: Use `scope=user` for simple user info retrieval.

### User Info Response Format

```json
{
  "id": 1189,
  "username": "Reno",
  "name": "",
  "avatar_template": "https://linux.do/user_avatar/linux.do/reno/288/4043_2.png",
  "active": true,
  "trust_level": 3,
  "silenced": false,
  "external_ids": null,
  "api_key": "9PfcPcFWFSR_oq6T1L-whdFS234z6W1Z29cvjxd_rwuzQU"
}
```

**Field Descriptions**:

| Field | Type | Description |
|---|---|---|
| `id` | integer | Unique user identifier (immutable) |
| `username` | string | Forum username |
| `name` | string | Display name (may be empty, mutable) |
| `avatar_template` | string | Avatar URL template (supports size placeholders) |
| `active` | boolean | Account active status |
| `trust_level` | integer | Trust level (0-4) |
| `silenced` | boolean | Whether user is muted |
| `external_ids` | object/null | External ID associations |
| `api_key` | string | API access key (may be included) |

### Rate Limits and Restrictions

| Limit Type | Details |
|---|---|
| API Rate Limit | Recommended: ≤60 requests/minute |
| Token Expiry | Access token typically valid for 3600 seconds (1 hour) |
| User Info Cache | Recommended 5-minute cache |
| 429 Response | Returned when rate limit exceeded |

**Security Notes**:
- Monitor for abuse patterns
- Single IP/account high-frequency requests may trigger rate limiting
- Implement exponential backoff for retries

### Technical Notes

- LinuxDo OAuth is based on Discourse platform extensions
- Compatible with standard OAuth 2.0 Authorization Code flow
- Response format is custom JSON (not strict OIDC standard)
- Avatar URLs support size replacement (e.g., `{size}` placeholder)

## External References

- [LinuxDo Connect Official Wiki](https://wiki.linux.do/Community/LinuxDoConnect) - Official documentation with code examples
- [LinuxDo Forum Tutorial](https://linux.do/t/topic/30578) - Community tutorial with step-by-step guide
- [LinuxDo Connect Docs](https://linux.do/t/topic/32752) - Detailed integration documentation
- [Dify Plugin Integration](https://marketplace.dify.ai/plugin/frederick/linuxdo) - Real-world integration example

## Caveats / Not Found

- Exact rate limit thresholds not officially documented (60 req/min is community recommendation)
- Token refresh endpoint behavior not explicitly documented
- Some scopes may have undocumented restrictions
- Response format may evolve as Connect.Linux.Do is actively developed
