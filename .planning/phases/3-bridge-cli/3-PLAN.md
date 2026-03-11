# Phase 3: Bridge & CLI — Plan

**Objective:** MCP Bridge for consuming external servers, CLI tools, production polish

**Dependencies:** Phase 2 (Exchange & Economy)

**Requirements covered:** BRD-01, BRD-02, BRD-03, BRD-04, BRD-05, SET-04

---

## Plan 1: MCP Bridge Module (BRD-01 to BRD-05)

### Tasks
- Implement MCP Client adapter using official mcp package
- Wrap external MCP servers as stateless AgenLang agents
- Wrapped agents speak signed AgenLang YAML
- Wrapped agents participate in CNP negotiation
- Wrapped agents meter Joules and produce SERs

### Implementation Details
- MCPBridge class for connecting to external MCP servers
- WrappedMCPAgent class that translates between MCP and AgenLang
- Tool calling, Joule metering, SER generation

---

## Plan 2: CLI Polish & Final Integration

### Tasks
- Complete CLI commands: agent start, discover, inspect
- Add configuration file support
- Add proper error handling and logging

---

## Success Criteria

1. ✓ MCP Client adapter can connect to external MCP servers
2. ✓ External MCP servers wrapped as stateless AgenLang agents
3. ✓ Wrapped agents speak signed AgenLang YAML
4. ✓ Wrapped agents participate in CNP negotiation
5. ✓ Wrapped agents meter Joules and produce SERs
