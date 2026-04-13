---
name: bob-shell-delegate
description: IBM Bob Shell CLI delegation skill for bounded subtask execution from Claude Code
---

# Bob-Shell-Delegate Skill

IBM Bob Shell CLI delegation skill for bounded subtask execution from Claude Code

## When to Use This Skill

Use this skill when you need to:
- understand bob-shell-delegate features, APIs, and workflows
- find concrete code examples before implementing or debugging
- navigate the official documentation quickly through categorized references

## Quick Reference

### High-Signal Examples

**Example 1** (bash):
```bash
echo $BOB_SHELL_CLI_IDE_SERVER_PORT
```

**Example 2** (json):
```json
{
  "mcpServers": {
    "server1": {
      "command": "python",
      "args": ["/path/to/server.py"],
      "env": {
        "API_KEY": "your_api_key"
      },
      "alwaysAllow": ["tool1", "tool2"],
      "disabled": false
    }
  }
}
```

**Example 3** (json):
```json
{
 "mcpServers": {
   "local-server": {
     "command": "node",
     "args": ["server.js"],
     "cwd": "/path/to/project/Bob",
     "env": {
       "API_KEY": "your_api_key"
     },
     "alwaysAllow": ["tool1", "tool2"]
   }
 }
}
```

**Example 4** (json):
```json
{
 "mcpServers": {
   "remote-server": {
     "url": "https://your-server-url.com/mcp",
     "headers": {
       "Authorization": "Bearer your-token"
     },
     "alwaysAllow": ["tool3"]
   }
 }
}
```

**Example 5** (json):
```json
{
  "mcpServers": {
    "puppeteer": {
      "command": "cmd",
      "args": [
        "/c",
        "npx",
        "-y",
        "@modelcontextprotocol/server-puppeteer"
      ]
    }
  }
}
```

### Key Usage Notes

**Pattern 1:** IBM BobPricingDocsEnterpriseThemeLanguageDownloadSearch⌘KShellWelcome to Bob ShellChangelogFrequently Asked QuestionsGetting startedInstallingUnins...

```
{
  "mcpServers": {
    "server1": {
      "command": "python",
      "args": ["/path/to/server.py"],
      "env": {
        "API_KEY": "your_api_key"
      },
      "alwaysAllow": ["tool1", "tool2"],
      "disabled": false
    }
  }
}
```

**Pattern 2:** IBM BobPricingDocsEnterpriseThemeLanguageDownloadSearch⌘KShellWelcome to Bob ShellChangelogFrequently Asked QuestionsGetting startedInstallingUnins...

```
bob -p "Explain this project"
```

**Pattern 3:** IBM BobPricingDocsEnterpriseThemeLanguageDownloadSearch⌘KShellWelcome to Bob ShellChangelogFrequently Asked QuestionsGetting startedInstallingUnins...

```
{
  "general": {
    "checkpointing": {
      "enabled": true
    }
  }
}
```

**Pattern 4:** 2025-06-22T10-00-00_000Z-my-file.txt-write_file

```
/restore <checkpoint_file>
```

**Pattern 5:** For example

```
/restore 2025-06-22T10-00-00_000Z-my-file.txt-write_file
```

**Pattern 6:** IBM BobPricingDocsEnterpriseThemeLanguageDownloadSearch⌘KShellWelcome to Bob ShellChangelogFrequently Asked QuestionsGetting startedInstallingUnins...

```
# Example: Start Bob Shell with sandbox mode enabled
bob --sandbox
```

**Pattern 7:** IBM BobPricingDocsEnterpriseThemeLanguageDownloadSearch⌘KShellWelcome to Bob ShellChangelogFrequently Asked QuestionsGetting startedInstallingUnins...

```
bob -s "analyze this shell script for potential security issues before execution"
```

**Pattern 8:** Single flag example

```
export SANDBOX_FLAGS="--security-opt label=disable"
bob -s "analyze this shell script for potential security issues before execution"
```

## Reference Files

This skill includes comprehensive documentation in `references/`:

- **shell.md** - Shell documentation

Use `view` to read specific reference files when detailed information is needed.

## Working with This Skill

### Start Here
Start with the getting_started or tutorials reference files for foundational concepts.

### For Specific Features
Use the appropriate category reference file (api, guides, etc.) for detailed information.

### For Code Examples
Use the high-signal examples above first, then open the matching reference file for full context.

## Notes

- This skill was automatically generated from official documentation
- Reference files preserve the structure and examples from source docs
- Code examples include language detection for better syntax highlighting
- Quick reference entries are filtered to avoid low-signal placeholders and inline tokens

## Updating

To refresh this skill with updated documentation:
1. Re-run the scraper with the same configuration
2. The skill will be rebuilt with the latest information
