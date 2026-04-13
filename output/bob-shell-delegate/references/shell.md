# Bob-Shell-Delegate - Shell

**Pages:** 25

---

## Frequently Asked Questions | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/faq

**Contents:**
- Frequently Asked Questions
- General
  - What is Bob?
  - How does Bob work?
  - What can Bob do?
  - What are the risks of using Bob?
  - Can I choose which model Bob uses?
  - Does IBM collect data from my prompts?
- Usage
  - How do I start a new task?

FeedbackFind answers to common questions about IBM Bob and Bob Shell.

Learn about version-specific updates for Bob Shell.

You can install Bob Shell an installation script, your package manager, or the command palette.

---

## MCP | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/configuration/mcp/mcp-bobshell

**Contents:**
- MCP
- What is MCP?
- Why use MCP?
- Configuring MCP servers
  - Edit MCP settings files
  - Configuration properties
- Transport types
  - STDIO transport
  - SSE transport
- Platform-specific examples

FeedbackBob Shell supports the Model Context Protocol (MCP), allowing you to extend Bob's capabilities by connecting to external services and tools. This guide explains how to configure and use MCP servers with Bob Shell.

An MCP (Model Context Protocol) server acts as a bridge between Bob and external services like databases, APIs, or custom scripts. With MCP, you can extend Bob's capabilities beyond its built-in features.

MCP servers provide Bob with:

You can manage MCP server configurations at two levels:

When a server name exists in both global and project configurations, the project-level configuration takes precedence.

Use Bob IDE, or another text editor, to modify your MCP settings files.

Refer to the following example:

Each server configuration requires one of these properties:

Optional properties include:

MCP supports two ways to communicate with servers:

STDIO transport runs servers locally on your machine:

Example configuration:

SSE transport connects to remote servers over HTTP/HTTPS:

Example configuration:

When using version managers like asdf or mise:

Learn about the telemetry data Bob Shell can collect, how it's used to improve the product, and how to enable or disable data collection.

Create automatic snapshots of your project before applying changes.

**Examples:**

Example 1 (json):
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

Example 2 (json):
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

Example 3 (json):
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

Example 4 (json):
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

---

## Troubleshooting Bob Shell | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/troubleshooting/troubleshoot

**Contents:**
- Troubleshooting Bob Shell
- Authentication
  - Certificate errors
- IDE integration
  - Connection fails
  - Connection fails in dev container
  - Failed to connect to IDE companion extension
  - Connection lost unexpectedly
  - Directory mismatch
  - No workspace folder open

FeedbackFind solutions to issues you might encounter when using Bob Shell.

Error: Unable to verify certificate

Cause: You are on a corporate network with a firewall that intercepts and inspects SSL/TLS traffic. This requires a custom root CA certificate to be trusted by Node.js.

Solution: Set the NODE_EXTRA_CA_CERTS environment variable to the absolute path of your corporate root CA certificate file:

Error: Bob Shell cannot connect to the IDE.

Cause: The Bob Shell Companion extension might not be installed or running, or Bob Shell might be running outside the workspace directory.

Error: Bob Shell cannot connect to the IDE when running inside a dev container.

Cause: The Bob Shell port is not forwarded from the dev container to the host machine.

Get the Bob Shell port from the terminal inside the dev container:

Example output: 42991

Open the Command Palette in your IDE and select Forward a Port.

Add the port shown in step 1 (for example, 42991).

Enable IDE integration:

Or check the connection status:

Error: 🔴 Disconnected: Failed to connect to IDE companion extension

Cause: The Bob Shell Companion extension is not installed, not enabled, or not running in your IDE.

Error: 🔴 Disconnected: IDE connection error. The connection was lost unexpectedly

Cause: The IDE connection was interrupted due to a network issue or IDE restart.

Error: 🔴 Disconnected: Directory mismatch

Cause: Bob Shell is running in a different directory than the workspace open in your IDE.

Error: 🔴 Disconnected: To use this feature, please open a workspace folder

Cause: No folder or workspace is open in your IDE.

Error: IDE integration is not supported in your current environment

Cause: Bob Shell is not running from within a supported IDE's integrated terminal.

Solution: Run Bob Shell from within a supported IDE's integrated terminal.

Error: Bob Shell ignores files you want it to access, or accesses files you want it to ignore.

Cause: The .bobignore file might have conflicting patterns, incorrect pattern order, or be in the wrong location. Changes might not have taken effect yet.

Error: Bob Shell settings changes do not take effect.

Cause: The settings file might be in the wrong location, have invalid JSON syntax, or be overridden by higher-priority configuration sources. Changes might not have taken effect yet.

Check the settings file location:

Verify the JSON syntax is valid (use a JSON validator).

Remember the configuration precedence order:

Restart Bob Shell after changing settings files.

Error: Custom instructions are not being applied to Bob Shell sessions.

Cause: Custom instruction files might be in the wrong location, have incorrect file extensions, or not be loaded into the current context.

Verify files are in the correct location:

Check that files have the correct extensions (.md, .txt, or .xml).

Use /memory refresh to reload all context files.

Use /memory show to verify the current context.

Error: command not found: bob

Cause: Bob Shell is not correctly installed or not in your system's PATH.

Verify Bob Shell is installed:

If not found, reinstall Bob Shell using the installation instructions.

Check that your shell's PATH includes the Bob Shell installation directory.

Error: Shell mode (! command) does not run commands.

Cause: You might not be typing ! at an empty prompt, lack necessary permissions, or the command itself might be invalid.

Error: Bob Shell responds slowly to requests.

Cause: Network connectivity issues, too many files loaded as context, or large binary files included in the context.

Error: Bob Shell consumes excessive memory.

Cause: Too many files loaded as context, large directories not excluded, or circular imports in memory files.

To see detailed logging information, start Bob Shell with the debug flag:

Or set the debug flag in your settings:

Run the following command to see your version of Bob Shell:

Non-interactive session:

Check Bob Shell logs for error messages:

Control which projects can use Bob Shell's full capabilities with trusted folder security.

**Examples:**

Example 1 (unknown):
```unknown
export NODE_EXTRA_CA_CERTS=/path/to/your/corporate-ca.crt
```

Example 2 (bash):
```bash
echo $BOB_SHELL_CLI_IDE_SERVER_PORT
```

Example 3 (unknown):
```unknown
/ide enable
```

Example 4 (unknown):
```unknown
/ide status
```

---

## Trusted folders | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/security/trusted-folders

**Contents:**
- Trusted folders
- Trusted folders
- How trusted folders work
- Impact of untrusted folders
  - Project settings are ignored
  - Environment variables are ignored
  - Extension management is restricted
  - Tool auto-approval is disabled
  - Automatic memory loading is disabled
  - MCP servers do not connect

FeedbackControl which projects can use Bob Shell's full capabilities with trusted folder security.

Trusted folders give you control over which projects can be used with Bob Shell. You must approve a folder before Bob Shell loads any project-specific configurations, protecting you from potentially malicious code.

When you run Bob Shell from a folder for the first time, a trust dialog appears automatically, prompting you to make a choice:

Your choice is saved in ~/.bob/trustedFolders.json, so you are only asked once per folder.

When a folder is untrusted, Bob Shell runs in restricted safe mode to protect you. Safe mode disables the following features:

The .bob/settings.json file from the project is not loaded. Safe mode prevents loading of custom tools and other potentially dangerous configurations.

Any .env files from the project are not loaded.

You cannot install, update, or uninstall extensions.

You are always prompted before any tool runs, even if you have auto-approval enabled globally.

Files are not automatically loaded into context from directories specified in local settings.

Bob Shell will not attempt to connect to any MCP servers.

Custom commands from .toml files are not loaded, including both project-specific and global user commands.

Granting trust to a folder unlocks the full functionality of Bob Shell for that workspace.

You can change trust decisions or view all your settings using these methods:

Run the /permissions slash command from within Bob Shell. The interactive dialog appears, allowing you to change the trust level for the current folder.

To see a complete list of all your trusted and untrusted folder rules, inspect the contents of the ~/.bob/trustedFolders.json file in your home directory.

Bob Shell determines trust using the following order of operations:

IDE trust signal: If you are using the IDE integration, Bob Shell first asks the IDE if the workspace is trusted. The IDE's response takes highest priority.

Local trust file: If the IDE is not connected, Bob Shell checks the ~/.bob/trustedFolders.json file.

Unlike interactive mode, non-interactive sessions never display the trust dialog. Bob Shell operates silently based on pre-existing trust decisions.

In non-interactive sessions, trust decisions are determined automatically in this order:

When a folder is untrusted in non-interactive mode, additional restrictions apply beyond those listed in "Impact of untrusted folders":

For secure automation and CI/CD pipelines, establish trust decisions before running non-interactive commands:

Since non-interactive mode defaults to trusted for folders without explicit decisions, pre-configuring trust is essential for security-sensitive environments.

Isolate Bob Shell operations in a secure sandbox environment to protect your host system.

Troubleshooting Bob Shell

Find solutions to issues you might encounter when using Bob Shell.

---

## Installing | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/getting-started/install-and-setup

**Contents:**
- Installing
- System requirements
  - Operating systems
  - Memory
  - Storage
  - Network
  - Node.js
  - Package manager or Bob IDE
- Installation
  - Using installation scripts

FeedbackYou can install Bob Shell an installation script, your package manager, or the command palette.

macOS, Linux, or Windows

Minimum 4 GB RAM (8 GB recommended)

Minimum 500 MB available disk space

Active internet connection

Version 22.15.0 or later

Install with terminal commands or the command palette

Choose to install Bob Shell with an installation script, your package manager, or the command palette.

Select your operating system, then copy and run the command to install Bob Shell.

If you have manually downloaded the Bob Shell package from the Releases page, you can install it by using one of the following package managers:

You must revise the following commands to use the actual path where you downloaded the file.

You must run the following Windows commands with Powershell.

You must have Bob IDE installed to use the command palette to install Bob Shell.

Install Bob Shell directly from the command palette:

Press Ctrl+Shift+P on Windows/Linux or Cmd+Shift+P on macOS.

Run the following command from the command palette to install Bob IDE:

Type and select the following command:

When using Bob Shell, you will be prompted to authenticate with your internet browser and IBMid. After authenticating, close your browser and return to your Bob Shell instance.

Frequently Asked Questions

Find answers to common questions about IBM Bob and Bob Shell.

Remove Bob Shell from your system using the appropriate method for your installation.

**Examples:**

Example 1 (unknown):
```unknown
curl -fsSL https://bob.ibm.com/download/bobshell.sh | bash
```

Example 2 (unknown):
```unknown
curl -fsSL https://bob.ibm.com/download/bobshell.sh | bash
```

Example 3 (unknown):
```unknown
powershell -ep Bypass 'irm -Uri "https://bob.ibm.com/download/bobshell.ps1" | iex'
```

Example 4 (unknown):
```unknown
run bobshell
```

---

## Memory files | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/configuration/memory-import

**Contents:**
- Memory files
- Overview
- Why use memory imports
- Basic usage
  - Import syntax
  - Supported path formats
- Working with imports
  - Basic import example
  - Nested imports
- Safety features

FeedbackBreak down large AGENTS.md files into smaller, reusable components using a simple import syntax.

Use the @ symbol followed by the path to the file you want to import:

Files can import other files, creating a hierarchical structure:

Where header.md might contain:

This creates a tree structure of imports:

The memory import processor includes several safety mechanisms to prevent common issues:

The processor automatically detects and prevents circular imports. If file-a.md imports file-b.md and file-b.md tries to import file-a.md, the processor detects this circular reference and prevents it.

Example circular import:

The validateImportPath function ensures that imports are only allowed from specified directories, preventing access to sensitive files outside the allowed scope.

To prevent infinite recursion, the processor has a configurable maximum import depth (default: 5 levels). Imports can be nested up to 5 levels deep.

The processor handles common errors gracefully:

If a referenced file doesn't exist, the import will fail with an error comment in the output:

Permission issues or other file system errors are handled with appropriate error messages:

The import processor uses the marked library to detect code blocks and inline code spans, ensuring that @ imports inside code regions are ignored:

Processes import statements in AGENTS.md content.

Returns: Object containing processed content and import tree

Validates import paths to ensure they are safe and within allowed directories.

Returns: Whether the import path is valid

Finds the project root by searching for a .git directory upwards from the given start directory.

Returns: The project root directory (or the start directory if no .git is found)

Enable debug mode to see detailed logging of the import process:

This outputs detailed information about:

Control which files Bob Shell can access by creating a `.bobignore` file in your project.

Learn about the telemetry data Bob Shell can collect, how it's used to improve the product, and how to enable or disable data collection.

**Examples:**

Example 1 (markdown):
```markdown
# Main AGENTS.md file

This is the main content.

@./components/instructions.md

More content here.

@./shared/configuration.md
```

Example 2 (markdown):
```markdown
# My AGENTS.md

Welcome to my project!

@./getting-started.md

## Features

@./features/overview.md
```

Example 3 (markdown):
```markdown
# main.md

@./header.md
@./content.md
@./footer.md
```

Example 4 (markdown):
```markdown
# Project Header

@./shared/title.md
```

---

## Integrating with Bob IDE | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/configuration/ide-integration

**Contents:**
- Integrating with Bob IDE
- Overview
- Getting started
- Benefits of IDE integration
  - Enhanced context awareness
  - Seamless code modifications
- Installation methods
  - Method 1: Automatic setup (recommended)
  - Method 2: Command-line installation
- Managing the connection

FeedbackConnect Bob Shell directly to your code editor for a seamless development experience. This integration enhances Bob Shell's capabilities by providing real-time workspace awareness and enabling powerful features like in-editor diff viewing.

Currently, Bob IDE and compatible editors are supported. Additional editor support may be added in future releases.

Without IDE integration, Bob Shell only knows about files you explicitly reference. With integration enabled, Bob Shell automatically gains:

This contextual awareness allows Bob Shell to provide more relevant assistance without requiring you to manually reference files.

When Bob Shell suggests code changes:

This workflow allows you to:

Choose the installation method that works best for you:

When you run Bob Shell inside Bob IDE's integrated terminal, it automatically detects the environment and offers to set up integration:

Selecting "Yes" will:

If you dismissed the automatic prompt or need to reinstall, use the built-in command:

To verify your connection and see what context Bob Shell has access to:

When Bob Shell suggests code modifications, you'll see them in your editor's diff viewer.

You have multiple ways to accept suggested changes:

To reject suggested changes:

You can edit the suggested code directly in the diff editor before accepting it. This allows you to:

For frequently repeated changes, select "Yes, allow always" in Bob Shell to auto-accept similar changes in the future.

Access Bob Shell features directly from Bob IDE's Command Palette (Cmd+Shift+P or Ctrl+Shift+P):

When using Bob Shell with macOS Seatbelt sandboxing:

When running Bob Shell in a Docker container:

Solution: Run Bob Shell from within a supported IDE's integrated terminal

Solution: Install the Bob Shell Companion extension manually from your IDE's marketplace

You can create custom modes to tailor Bob's behavior to specific tasks or workflows. Custom modes in Bob Shell work similarly to Bob IDE modes.

Control which files Bob Shell can access by creating a `.bobignore` file in your project.

**Examples:**

Example 1 (unknown):
```unknown
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Bob Shell       │────▶│  Bob IDE        │────▶│  Your codebase  │
│  suggests       │     │  diff viewer    │     │  with changes   │
│  changes        │     │  shows changes  │     │  applied        │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

Example 2 (lua):
```lua
┌─────────────────────────────────────────────────────────────────────────────┐
│ > Do you want to connect Bob IDE to Bob Shell?                               │
│ If you select Yes, we'll install an extension that allows the CLI to ac ... │
│                                                                             │
│   1. Yes                                                                    │
|   2. No                                                                     │
|   3. No, don't ask again                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

Example 3 (unknown):
```unknown
/ide install
```

Example 4 (unknown):
```unknown
/ide status
```

---

## Changelog | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/changelog

**Contents:**
- Changelog
- 1.0.1
- New Features

FeedbackLearn about version-specific updates for Bob Shell.

Terminal-based AI assistance

Bring IBM Bob's AI capabilities directly to your command line. Get intelligent assistance for command-line tasks and terminal-based workflows. Access the same context awareness and reasoning from your development partner, Bob.Learn more →

Interactive and non-interactive sessions

Choose the right session type for your workflow. Use interactive sessions for conversational experiences with complex tasks. Use non-interactive sessions for automation and scripting scenarios. Invoke Bob Shell programmatically in automated workflows.Learn more →

Access purpose-built modes optimized for command-line scenarios. Code mode generates, modifies, and refactors code from the command line. Ask mode provides answers about your codebase and development questions. Plan mode helps design and plan implementations before running. Advanced mode provides extended capabilities including MCP tools.Learn more →

Accomplish complex terminal-based tasks efficiently. Read, write, and manipulate files directly from the command line. Run shell commands with intelligent error handling and validation. Monitor and control running processes and system resources.Learn more →

MCP (Model Context Protocol) integration

Extend Bob Shell's capabilities with custom tools. Connect to databases and APIs from the terminal. Access specialized development and operations tools. Integrate with your organization's internal systems. Create custom automation workflows for DevOps tasks.Learn more →

Custom modes and slash commands

Extend functionality for your team's needs. Define custom modes for specialized workflows. Create reusable command shortcuts. Build team-specific automation patterns. Standardize development processes across your organization.Learn more →

Editor terminal support

Run Bob Shell inside terminal views of supported editors. Seamlessly integrate with your development environment.Learn more →

Bob Shell brings IBM Bob's AI capabilities to your command line.

Frequently Asked Questions

Find answers to common questions about IBM Bob and Bob Shell.

---

## Uninstalling | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/getting-started/uninstalling-bobshell

**Contents:**
- Uninstalling
- Uninstall Bob Shell
- Remove configuration files (optional)
  - On this page

FeedbackRemove Bob Shell from your system using the appropriate method for your installation.

To uninstall Bob Shell, use the corresponding uninstall command for the package manager you used when you installed Bob Shell:

After uninstalling Bob Shell, remove configuration files and data:

This permanently deletes your Bob Shell settings and any saved data.

You can install Bob Shell an installation script, your package manager, or the command palette.

Starting an interactive session

Interactive sessions provide a conversational interface to Bob directly in your terminal, allowing real-time assistance with your development tasks.

**Examples:**

Example 1 (unknown):
```unknown
npm uninstall -g bobshell
```

Example 2 (unknown):
```unknown
pnpm remove -g bobshell
```

Example 3 (unknown):
```unknown
yarn global remove bobshell
```

Example 4 (markdown):
```markdown
# Remove Bob Shell configuration directory
rm -rf ~/.bob
```

---

## Custom modes | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/configuration/custom-modes-bobshell

**Contents:**
- Custom modes
- Why use custom modes in Bob Shell
- What's included in a custom mode
- Available tools
  - Available tool groups
- Creating custom modes
  - Configuration files
    - Global modes
    - Project-specific modes
  - Command-line mode selection

FeedbackYou can create custom modes to tailor Bob's behavior to specific tasks or workflows. Custom modes in Bob Shell work similarly to Bob IDE modes.

Custom modes in Bob Shell use the same core structure as Bob IDE modes:

Bob Shell uses the same configuration format as Bob IDE, supporting both YAML (preferred) and JSON formats.

Create or edit ~/.bob/custom_modes.yaml for modes available across all projects:

Create or edit .bob/custom_modes.yaml in your project root:

Specify a mode when starting Bob Shell:

In interactive mode, switch modes using slash commands:

Create a safety-focused mode for production environments:

Create a mode for shell script development:

Control which commands a mode can run by omitting the command group:

Use Bob Shell's allowed tools configuration with custom modes in your settings file:

Create modes that work well in both interactive and non-interactive sessions:

Use modes in non-interactive mode:

Create mode-specific instruction files in .bob/rules-{mode-slug}/:

Example instruction file (.bob/rules-shell-debug/01-environment-checks.md):

Alternatively, use a single file .bobrules-{mode-slug} in your workspace root.

Mode configurations are applied in this order:

Combine custom modes with Bob Shell's sandbox feature for safe experimentation:

When migrating custom modes from Bob IDE to Bob Shell:

When adapting Bob IDE modes for Bob Shell:

Original Bob IDE mode:

Adapted for Bob Shell:

Custom rules influence how Bob Shell responds to your requests in the terminal environment, aligning output with your specific preferences and project requirements. You can control coding style, documentation approach, and decision-making processes.

Integrating with Bob IDE

Connect Bob Shell directly to your code editor for a seamless development experience. This integration enhances Bob Shell's capabilities by providing real-time workspace awareness and enabling powerful features like in-editor diff viewing.

**Examples:**

Example 1 (yaml):
```yaml
customModes:
  - slug: shell-debug
    name: 🐛 Shell Debugger
    roleDefinition: >-
      You are a debugging specialist focused on command-line troubleshooting.
      You excel at analyzing shell output, environment variables, and system logs.
    whenToUse: Use for debugging shell scripts, command failures, and environment issues.
    customInstructions: |-
      When debugging:
      - Always check environment variables first
      - Examine command exit codes
      - Review relevant log files
      - Test commands in isolation before suggesting fixes
    groups:
      - read
      - command
      - browser
```

Example 2 (yaml):
```yaml
customModes:
  - slug: deploy-helper
    name: 🚀 Deployment Assistant
    roleDefinition: You are a deployment specialist for this project's infrastructure.
    whenToUse: Use for deployment tasks, infrastructure changes, and release management.
    customInstructions: |-
      Deployment guidelines:
      - Always verify the target environment before running commands
      - Check for running processes that might be affected
      - Validate configuration files before applying changes
      - Create backups before destructive operations
    groups:
      - read
      - - edit
        - fileRegex: \.(yaml|yml|sh|env)$
          description: Configuration and script files only
      - command
```

Example 3 (sass):
```sass
# Start Bob Shell in a specific mode
bob --chat-mode=shell-debug

# Combine with other options
bob --chat-mode=deploy-helper --sandbox
```

Example 4 (elixir):
```elixir
# Switch to a custom mode
/mode shell-debug

# Or use the mode's slug directly
/shell-debug
```

---

## Telemetry data | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/configuration/telemetry-data-shell

**Contents:**
- Telemetry data
- Collected data
- How to enable or disable telemetry in Bob Shell
  - On this page

FeedbackLearn about the telemetry data Bob Shell can collect, how it's used to improve the product, and how to enable or disable data collection.

IBM Bob does not collect telemetry data by default. You must opt in to enable telemetry data collection. When enabled:

Telemetry data helps IBM learn how to improve Bob. Your cooperation is greatly appreciated.

The table below summarizes the categories of usage data that IBM Bob can collect.

With a Bob Shell session open, type /settings.

Scroll down and select Enable Usage Metrics.

Press enter to toggle between true (Enabled) and false (Disabled). You can press tab to save settings globally or for a user.

Break down large AGENTS.md files into smaller, reusable components using a simple import syntax.

Bob Shell supports the Model Context Protocol (MCP), allowing you to extend Bob's capabilities by connecting to external services and tools. This guide explains how to configure and use MCP servers with Bob Shell.

---

## Keyboard shortcuts | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/configuration/keyboard-shortcuts

**Contents:**
- Keyboard shortcuts
- Quick reference
- Navigation shortcuts
  - Cursor movement
  - History navigation
- Editing shortcuts
  - Text deletion
  - Text manipulation
- Application control
  - Session management

FeedbackFind all available shortcuts by function, with platform-specific variations where applicable.

Efficiently move through text and command history:

Efficiently edit and modify text:

Control Bob Shell's core functionality:

Access specialized functionality:

On macOS, many shortcuts use the Option key (also called Alt or ⌥) instead of Ctrl for word-based operations:

Some shortcuts may be intercepted by your terminal emulator before reaching Bob Shell:

You can configure Bob Shell to match your workflow preferences.

Custom rules influence how Bob Shell responds to your requests in the terminal environment, aligning output with your specific preferences and project requirements. You can control coding style, documentation approach, and decision-making processes.

---

## Starting an interactive session | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/getting-started/start-bobshell-interactive

**Contents:**
- Starting an interactive session
- To start an interactive session:
- Basic usage
  - Interact with Bob Shell
  - Reference files
- Use slash commands
- View file changes
- Advanced features
  - Tool approvals
  - Multi-turn conversations

FeedbackInteractive sessions provide a conversational interface to Bob directly in your terminal, allowing real-time assistance with your development tasks.

Open a new terminal window.

When you start Bob Shell for the first time, you must login with your IBMid and accept the license agreement.

Navigate to the main directory of your project.

To start a Bob Shell interactive session, run:

Use the @ symbol to reference files in your project:

This tells Bob Shell to read and analyze the specified file before responding.

Type / to access a menu of available commands:

For a complete list of available commands, see Slash commands in Bob Shell.

When Bob Shell needs to modify files, it will show you the proposed changes:

For security, Bob Shell requires your approval before:

You can approve or decline each action individually when prompted.

Bob Shell maintains context throughout your conversation, allowing you to:

Interactive session works best for:

Remove Bob Shell from your system using the appropriate method for your installation.

Starting a non-interactive session

Non-interactive session provide a method to use Bob Shell directly from the command line without entering an interactive session. Use for automation, scripting, and batch processing tasks.

**Examples:**

Example 1 (elixir):
```elixir
Explain the functionality in @src/main.js
```

---

## Usage examples | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/getting-started/bobshell-examples

**Contents:**
- Usage examples
- Fixing errors in shell commands
- Code explanation and improvement
- Creating new files and features
- Debugging assistance
- Documentation generation
- Learning new concepts
  - On this page

FeedbackPractical examples showing how to use Bob Shell for debugging, code improvement, file creation, documentation generation, and learning new concepts.

When you encounter errors in your shell commands, Bob Shell can help diagnose and fix them:

Bob Shell can help you understand and improve existing code:

Use Bob Shell to help you create new components or features:

Bob Shell can help you debug issues in your code:

Generate documentation for your code using Bob Shell:

Use Bob Shell to learn about new technologies or concepts:

Starting a non-interactive session

Non-interactive session provide a method to use Bob Shell directly from the command line without entering an interactive session. Use for automation, scripting, and batch processing tasks.

Learn how Bob Shell uses specialized tools to read files, edit code, run commands, and interact with your development environment from the command line.

**Examples:**

Example 1 (markdown):
```markdown
# Navigate to your project directory
cd your-project/

# Start Bob Shell
bob

# Switch to shell mode
> !

# Type in the command that's causing an error
> make build

# When you see an error message like 'No rule to make target `xxx', needed by `yyy'.'

# Press ESC or enter '!' again to exit shell mode 

# Ask Bob Shell for help
> Help me to fix the error
```

Example 2 (elixir):
```elixir
# Start Bob Shell in your project directory
bob

# Ask for an explanation of a specific file
> Explain what @src/utils.js does and how it works

# Request improvements to your code
> Review @src/api.js and suggest improvements for error handling
```

Example 3 (markdown):
```markdown
# Start Bob Shell in your project directory
bob

# Ask for help creating a new component
> Create a React component for a user profile page that displays name, email, and avatar

# Generate a utility function
> Write a utility function that formats dates in YYYY-MM-DD format
```

Example 4 (elixir):
```elixir
# Start Bob Shell in your project directory
bob

# Share error logs with Bob Shell
> I'm getting this error when running my app: "TypeError: Cannot read property 'map' of undefined". Here's the relevant code: @src/components/List.js

# Or pipe error output directly to Bob Shell
# In your terminal (not in Bob Shell)
npm run start 2>&1 | bob -p "Help me understand and fix this error"
```

---

## Tools | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/core-concepts/tools

**Contents:**
- Tools
- Tool workflow
- Tool categories
  - Read tools
  - Write tools
  - Command tools
  - MCP tools
  - Mode tools
  - Question tools
  - On this page

FeedbackLearn how Bob Shell uses specialized tools to read files, edit code, run commands, and interact with your development environment from the command line.

When you describe what you want to accomplish in natural language, Bob Shell will:

Bob Shell's tools are organized into categories based on their primary function. Understanding these categories helps you know what Bob Shell can do and how it accomplishes tasks.

Access file content and understand code structure without making changes.

When Bob Shell uses read tools: When you ask Bob Shell to review code, find specific patterns, or understand project structure.

Create new files or modify existing code with precision.

When Bob Shell uses write tools: When you ask Bob Shell to create files, implement features, fix bugs, or refactor code.

Run commands and perform system operations in your terminal.

When Bob Shell uses command tools: When you ask Bob Shell to run commands, install packages, run scripts, or complete system operations.

Extend Bob Shell's capabilities through Model Context Protocol servers.

When Bob Shell uses MCP tools: When you've configured MCP servers and need to access their specialized capabilities.

Switch between different Bob Shell modes for specialized tasks.

When Bob Shell uses mode tools: When the current task would benefit from a different mode's specialized capabilities.

Gather additional information needed to complete tasks.

Practical examples showing how to use Bob Shell for debugging, code improvement, file creation, documentation generation, and learning new concepts.

You can configure Bob Shell to match your workflow preferences.

---

## Security guidelines | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/security/bob-security-guidance

**Contents:**
- Security guidelines
- Security checklist
- File access restrictions
  - Setting up .bobignore
  - Understanding limitations
- Trusted folders
- Auto-approve settings
  - High-risk auto-approve settings
- Handling secrets securely
  - Best practices for secrets management

FeedbackBob has capabilities for coding and system interaction. To use safely, follow these guidelines.

You can control Bob's file access by configuring which directories and file types it can interact with. The .bobignore file uses the same syntax as .gitignore and should be one of the first security measures you implement when setting up Bob.

Add patterns for sensitive files and directories. Include patterns for any non-approved data types.

Bob actively monitors the .bobignore file, and any changes are automatically applied. For detailed information, see Using .bobignore to Control File Access.

While .bobignore effectively controls Bob's access through its tools, it has some important limitations:

Review the complete key limitations and scope to understand how .bobignore protects your files.

Bob Shell uses trusted folders to control which projects it can access. You must explicitly approve a folder before Bob Shell loads project-specific configurations, protecting you from potentially malicious code.

When you run Bob Shell from a folder for the first time, you can choose to:

Untrusted folders operate in safe mode with significant restrictions:

For complete details on how trusted folders work, managing trust settings, and best practices, see Trusted folders.

With Bob, you can automatically approve various actions without confirmation prompts. While this speeds up your workflow, it significantly increases security risks.

Auto-approve settings bypass confirmation prompts, giving Bob direct access to your system. This can result in data loss, file corruption, or worse. Command line access is particularly dangerous, as it can potentially run harmful operations.

Always review Bob's output to ensure it's accurate and that any generated code will act as intended. Never inherently trust output from any AI system.

For detailed information on each setting and its security implications, see Configuring Bob Shell.

Never provide secrets directly to any AI system, including Bob. Even temporary inclusion of secrets in code can lead to unintended exposure.

AI systems should not leverage credentials that allow them to act on your behalf without your intervention and review. When AI systems need to act on your behalf:

Model Context Protocol (MCP) extends Bob's functionality by connecting to external tools and services. While powerful, MCP connections require careful security consideration.

MCP uses a client-server architecture:

When using MCP servers, practice the following guidelines:

Remote MCP servers must adhere to the same security requirements as any traditional server infrastructure, including endpoint protection, network restrictions, and proper access controls.

For shared MCP servers, ensure proper auditability and accountability so actions can be traced.

By following these security best practices, you can leverage Bob's powerful capabilities while maintaining a secure development environment.

Switch between IBM instances and teams using the /instance command.

Isolate Bob Shell operations in a secure sandbox environment to protect your host system.

**Examples:**

Example 1 (markdown):
```markdown
# Example .bobignore patterns
.env
secrets/
*.key
config/credentials.json
```

---

## Custom rules | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/configuration/bobshell-custom-rules

**Contents:**
- Custom rules
- What are custom rules?
- Rule scopes
- Configuration methods
  - File-based configuration
  - Directory-based configuration
- Rule priority
- Writing effective rules
  - Be specific and actionable
  - Use clear structure

FeedbackCustom rules influence how Bob Shell responds to your requests in the terminal environment, aligning output with your specific preferences and project requirements. You can control coding style, documentation approach, and decision-making processes.

Custom rules extend Bob Shell's default behavior by defining preferences, constraints, and guidelines that direct how Bob Shell approaches tasks to match your needs when working in the terminal environment.

Bob Shell supports two rule scopes that determine where your rules apply:

Use global rules for personal or organization-wide standards. Use workspace rules for project-specific requirements.

Bob Shell uses the same custom rules system as IBM Bob IDE.

The simplest approach uses single files in your workspace root:

Create a .bobrules file:

For better organization, use directories:

Linux/macOS: ~/.bob/rules/ Windows: %USERPROFILE%\.bob\rules\

Create workspace rules:

Bob Shell combines rules from multiple sources in this order:

Within each level, mode-specific rules load before general rules. Workspace rules can override global rules.

Good: "Always use relative paths when suggesting file operations in the terminal"

Avoid: "Use good paths"

Organize rules by topic:

Target specific modes with dedicated directories:

For team standardization, you can use an AGENTS.md file in your workspace root:

Use workspace .bob/rules/ directories under version control:

This ensures consistent behavior across team members using Bob Shell for specific projects.

Distribute global rules to team members:

You can combine both approaches:

Find all available shortcuts by function, with platform-specific variations where applicable.

You can create custom modes to tailor Bob's behavior to specific tasks or workflows. Custom modes in Bob Shell work similarly to Bob IDE modes.

**Examples:**

Example 1 (markdown):
```markdown
# In your project root
echo "Use 4 spaces for indentation" > .bobrules
```

Example 2 (unknown):
```unknown
.bob/
├── rules/              # General rules
│   └── coding-style.md
└── rules-code/         # Code mode rules
    └── typescript.md
```

Example 3 (bash):
```bash
mkdir -p .bob/rules
echo "# Project standards" > .bob/rules/coding-style.md
```

Example 4 (markdown):
```markdown
# Linux/macOS
mkdir -p ~/.bob/rules
echo "# Global standards" > ~/.bob/rules/coding-standards.md

# Windows
mkdir %USERPROFILE%\.bob\rules
echo # Global standards > %USERPROFILE%\.bob\rules\coding-standards.md
```

---

## Starting a non-interactive session | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/getting-started/start-bobshell-non-interactive

**Contents:**
- Starting a non-interactive session
- To start a non-interactive session:
- Basic usage
  - Providing prompts to Bob Shell
  - Pipe content as input
  - Save results to a file
  - Reference project files
- Advanced options
  - Enable file modifications
  - Format output for processing

FeedbackNon-interactive session provide a method to use Bob Shell directly from the command line without entering an interactive session. Use for automation, scripting, and batch processing tasks.

Open a new terminal window.

Navigate to the main directory of your project.

Run the bob -p command to start Bob Shell in your terminal.

Before starting a non-interactive session for the first time, you must accept the license agreement. You can do this by either:

Use the bob -p command to get Bob to address your prompt:

You can pipe text content to Bob Shell:

Redirect the output to save results:

Use the @ symbol to reference files in your project:

By default, Bob Shell only uses non-destructive tools (like reading files) in non-interactive session. To enable writing and updating files, add the --yolo flag:

Even with the --yolo flag enabled, Bob Shell will not write or update files outside the directory where it was started.

The output contains both Bob Shell's answer and its thinking steps. For easier processing, add instructions to format the output:

Non-interactive session works best for:

Starting an interactive session

Interactive sessions provide a conversational interface to Bob directly in your terminal, allowing real-time assistance with your development tasks.

Practical examples showing how to use Bob Shell for debugging, code improvement, file creation, documentation generation, and learning new concepts.

**Examples:**

Example 1 (unknown):
```unknown
bob -p "Explain this project"
```

Example 2 (unknown):
```unknown
bob -p "Explain this project"
```

Example 3 (unknown):
```unknown
cat buildError.txt | bob -p "Explain this build error"
```

Example 4 (elixir):
```elixir
bob -p "Review @bigFile.java" > review.md
```

---

## Checkpointing | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/features/checkpointing

**Contents:**
- Checkpointing
- Why use checkpointing?
- How checkpointing works
- Enabling checkpointing
  - Settings file (persistent)
- Managing checkpoints
  - Viewing available checkpoints
  - Restoring a checkpoint
- Best practices
- Limitations

FeedbackCreate automatic snapshots of your project before applying changes.

When you approve a file-modifying operation (such as write_file or replace), Bob Shell automatically:

Creates a Git snapshot in a shadow repository (~/.bob/history/<project_hash>)

Note: This shadow repository is separate from your project's Git repository and won't interfere with your normal Git workflow.

Saves your conversation history up to that point

Records the tool call that was about to run

This three-part checkpoint allows you to:

All checkpoint data is stored locally on your machine:

Checkpointing is disabled by default. You can enable it in two ways:

To enable checkpointing for all sessions:

To see all saved checkpoints for your current project:

Bob Shell will display a list of checkpoint files with names that include:

Example: 2025-06-22T10-00-00_000Z-my-file.txt-write_file

To restore your project to a specific checkpoint:

Bob Shell supports the Model Context Protocol (MCP), allowing you to extend Bob's capabilities by connecting to external services and tools. This guide explains how to configure and use MCP servers with Bob Shell.

Create custom slash commands to automate workflows and standardize team practices.

**Examples:**

Example 1 (json):
```json
{
  "general": {
    "checkpointing": {
      "enabled": true
    }
  }
}
```

Example 2 (typescript):
```typescript
/restore <checkpoint_file>
```

Example 3 (unknown):
```unknown
/restore 2025-06-22T10-00-00_000Z-my-file.txt-write_file
```

---

## Instance command | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/features/instance-command

**Contents:**
- Instance command
- Why use the instance command?
- How the instance command works
- Switching instances or teams
- Understanding the instance table
- Troubleshooting
  - Cannot cancel during first-time setup
  - Instance not appearing
  - Selection not persisting
  - On this page

FeedbackSwitch between IBM instances and teams using the /instance command.

Type /instance to open an interactive selection dialog where you can view and select from your available instances and teams.

When you type /instance, an interactive table appears showing your available instances and teams. Navigate through options using keyboard controls and select the instance or team you want to use.

Type /instance to open the selection dialog.

Navigate through available options using the arrow keys.

The highlighted option is marked with ●, and your current selection is marked with ★.

Press Enter to select the highlighted instance or team.

A success message displays your selection. Authentication refreshes automatically, and your selection persists across sessions.

During first-time setup, you must select an instance before you can use Bob Shell. The Esc key is disabled until you complete the initial configuration.

The instance selection table displays different information depending on your plan type:

Enterprise users see additional team information:

Individual plan users work with instances only:

Create custom slash commands to automate workflows and standardize team practices.

Bob has capabilities for coding and system interaction. To use safely, follow these guidelines.

---

## Configuring | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/configuration/configuring

**Contents:**
- Configuring
- Getting started
- Configuration system
  - How configuration works
  - Settings file locations
- Core settings categories
  - General settings
  - UI settings
  - Context settings
  - Tools settings

FeedbackYou can configure Bob Shell to match your workflow preferences.

You can configure Bob Shell using:

Bob Shell uses a layered configuration system where settings from different sources are combined according to a specific precedence order:

When the same setting is defined in multiple places, the higher-priority source takes precedence.

Bob Shell looks for settings files in these locations:

Bob Shell settings are organized into categories. Each category contains related settings that control specific aspects of Bob Shell's behavior.

Control basic Bob Shell behavior and preferences.

Customize Bob Shell's appearance and interface elements.

Control how Bob Shell manages project context and memory.

Configure how Bob Shell uses and manages tools.

Configure Model Context Protocol server connections.

For each MCP server, you can configure:

Pass these arguments when starting Bob Shell to override settings for that session:

Context files (like AGENTS.md) provide instructions to the AI model. These files are loaded hierarchically:

Sandboxing provides security when running potentially unsafe operations:

You can create custom sandbox environments:

Build and use your custom sandbox:

The create-pr command is not compatible with Sandbox sessions.

Bob Shell collects anonymous usage statistics to improve the product. This includes:

No personal information, prompt content, or file content is collected.

To opt out, add this to your settings:

Learn how Bob Shell uses specialized tools to read files, edit code, run commands, and interact with your development environment from the command line.

Find all available shortcuts by function, with platform-specific variations where applicable.

**Examples:**

Example 1 (markdown):
```markdown
# Example: Start Bob Shell with sandbox mode enabled
bob --sandbox
```

Example 2 (unknown):
```unknown
/etc/bobshell/settings.json
```

Example 3 (yaml):
```yaml
C:\ProgramData\bobshell\settings.json
```

Example 4 (unknown):
```unknown
/Library/Application Support/Bob Shell/settings.json
```

---

## Welcome to Bob Shell | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell

**Contents:**
- Welcome to Bob Shell
- What you can do with Bob Shell
  - Automate scripts
  - Execute commands
  - Generate documentation
  - Troubleshoot issues
  - Analyze logs
  - Scaffold projects
- Key capabilities
  - Flexible ways to run Bob Shell

FeedbackBob Shell brings IBM Bob's AI capabilities to your command line.

As a terminal-based interface, Bob Shell provides AI-assistance for command-line tasks, script automation, and terminal-based workflows.

Bob Shell delivers the same context awareness and reasoning-focused approach from IBM Bob, but optimized for shell environments and automated processes.

Generate and optimize shell scripts for complex automation tasks.

Run terminal commands with AI-powered assistance and validation.

Create comprehensive documentation for scripts and workflows.

Debug command failures and resolve terminal-based problems.

Parse and analyze log files to identify issues and patterns.

Initialize new projects and generate boilerplate code from the terminal.

Bob Shell adapts to your workflow with flexible ways to work:

Engage in conversational sessions directly in your terminal

Run commands or tasks for automation and scripting

Seamlessly integrate into automated processes and workflows

Run Bob Shell inside terminal views of supported editors

Interactive sessions provide a conversational experience for complex tasks, while non-interactive sessions enable automation and scripting scenarios where Bob Shell can be invoked programmatically.

Use interactive sessions for exploratory tasks and problem-solving. Switch to non-interactive sessions when you need to automate repetitive workflows or integrate Bob into scripts.

Bob Shell includes purpose-built modes that optimize behavior for different command-line scenarios:

Generate, modify, and refactor code from the command line.

Get answers about your codebase and development questions.

Design and plan implementations before running them.

Access extended capabilities including MCP tools.

Each mode is optimized for specific terminal-based development scenarios, allowing you to work efficiently without changing your communication approach.

Bob Shell provides comprehensive tools designed for terminal environments:

Read, write, and manipulate files directly from the command line.

Run shell commands with intelligent error handling and validation.

Monitor and control running processes and system resources.

Extend capabilities through the MCP (Model Context Protocol) framework for custom integrations.

These tools work seamlessly together, so you can accomplish complex terminal-based tasks without switching contexts or applications.

Model Context Protocol (MCP) extends Bob Shell's capabilities with custom tools tailored for command-line workflows:

MCP integration in Bob Shell can be used for DevOps workflows. Connect to monitoring systems, deployment tools, and infrastructure APIs to create comprehensive automation solutions.

Use Bob Shell for automation tasks:

Automate repetitive development tasks with intelligent shell scripts.

Process multiple files or projects in automated workflows.

Extend Bob Shell's functionality with custom modes and slash commands:

Ready to bring AI assistance to your terminal? Follow these steps to get up and running:

Start by using Bob Shell for a task you're already familiar with. This helps you understand how Bob Shell interprets commands and provides assistance in a terminal context.

Now that you understand what Bob Shell can do, explore these resources to deepen your knowledge:

Learn how to use Bob Shell in interactive sessions for complex tasks.

Discover how to use Bob Shell in scripts and automation workflows.

Configure Bob Shell settings and customize your experience.

Master Bob Shell's slash commands for efficient terminal workflows.

Find answers to common questions about Bob Shell.

Learn about version-specific updates for Bob Shell.

---

## Sandboxing | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/security/sandboxing

**Contents:**
- Sandboxing
- Why use sandboxing?
- Sandboxing methods
  - macOS Seatbelt (macOS only)
  - Container-based (Docker/Podman)
- Configuration
  - Command flags
  - Environment variables
  - Settings file
  - macOS Seatbelt profiles

FeedbackIsolate Bob Shell operations in a secure sandbox environment to protect your host system.

Sandboxing isolates potentially dangerous operations, such as shell commands or file modifications, from your host system.

Sandboxing provides several key benefits:

Choose from the following options to create a sandbox environment:

You can use the default sandbox-exec utility.

Default profile: permissive-open - restricts writes outside your project directory while allowing most other operations.

Cross-platform sandboxing with complete process isolation using Docker or Podman containers.

Container-based sandboxing requires building the sandbox image locally or using a published image from your organization's registry.

You can enable sandboxing through command flags, environment variables, or configuration files.

Enable sandboxing for a single command using the -s or --sandbox flag. Use command flags for one-time testing or when you need sandboxing for a specific command without affecting your default workflow.

Set the BOB_SHELL_SANDBOX environment variable. Use environment variables when you want sandboxing enabled for an entire terminal session or specific project without modifying configuration files.

You can also specify the sandbox type:

Add the sandbox option to the tools object in your settings.json. Use the settings file for persistent, project-wide sandboxing that applies to all team members and sessions.

You can also use a specific sandbox type:

Configuration precedence (highest to lowest):

Control the level of restriction using the SEATBELT_PROFILE environment variable:

For container-based sandboxing, inject custom flags into the docker or podman command using the SANDBOX_FLAGS environment variable. Use this when you need more control over container resources, security settings, or volume mounts, best for advanced users who need to customize memory limits, CPU allocation, or SELinux configurations for specific workloads.

Multiple flags example:

Bob Shell automatically handles user permissions on Linux to ensure files created in the sandbox have the correct ownership. Use this to control file ownership mapping between the container and host system, best for Linux environments where you need to ensure files created in the sandbox have correct permissions or when troubleshooting permission issues.

Override this behavior if needed:

While sandboxing significantly improves security, it has some important limitations to be aware of:

Bob has capabilities for coding and system interaction. To use safely, follow these guidelines.

Control which projects can use Bob Shell's full capabilities with trusted folder security.

**Examples:**

Example 1 (unknown):
```unknown
bob -s "analyze this shell script for potential security issues before execution"
```

Example 2 (sass):
```sass
export BOB_SHELL_SANDBOX=true
bob "analyze this shell script for potential security issues before execution"
```

Example 3 (sass):
```sass
export BOB_SHELL_SANDBOX=docker  # or podman, or sandbox-exec
```

Example 4 (json):
```json
{
  "tools": {
    "sandbox": true
  }
}
```

---

## Ignoring files | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/configuration/ignoring-files

**Contents:**
- Ignoring files
- Overview
- Why use .bobignore?
- How .bobignore works
- Pattern syntax
- Getting started
  - Creating a .bobignore file
  - Common exclusion patterns
- Pattern examples
  - Excluding specific directories

FeedbackControl which files Bob Shell can access by creating a `.bobignore` file in your project.

When you add paths to your .bobignore file, Bob Shell tools that respect this file will automatically exclude matching files and directories from their operations. For example, when using the read_many_files command, any paths in your .bobignore file will be skipped.

Changes to your .bobignore file require restarting your Bob Shell session to take effect.

The .bobignore file follows the same pattern syntax as .gitignore:

Here are some common patterns you might want to add to your .bobignore file:

To exclude entire directories and their contents:

Wildcards let you match multiple files with similar patterns:

You can override exclusions for specific files:

You can create sophisticated exclusion rules by combining patterns:

If Bob Shell seems to be ignoring files you want it to access, or accessing files you want it to ignore:

Integrating with Bob IDE

Connect Bob Shell directly to your code editor for a seamless development experience. This integration enhances Bob Shell's capabilities by providing real-time workspace awareness and enabling powerful features like in-editor diff viewing.

Break down large AGENTS.md files into smaller, reusable components using a simple import syntax.

**Examples:**

Example 1 (unknown):
```unknown
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Your project   │────▶│  .bobignore     │────▶│  Files Bob Shell │
│  files          │     │  filter         │     │  can access     │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

Example 2 (sql):
```sql
# From your project root
touch .bobignore
echo "# Files to ignore" > .bobignore
echo "secrets/" >> .bobignore
```

Example 3 (markdown):
```markdown
# Sensitive information
.env
secrets/
*password*
*credential*
*apikey*

# Large directories
node_modules/
.git/
dist/
build/

# Binary and media files
*.zip
*.tar.gz
*.mp4
*.jpg
*.png

# Log files
*.log
logs/
```

Example 4 (markdown):
```markdown
# Exclude the packages directory and all its contents
/packages/

# Exclude all node_modules directories anywhere in the project
**/node_modules/

# Exclude the dist directory but only at the root level
/dist/
```

---

## Slash commands | Docs | IBM Bob

**URL:** https://bob.ibm.com/docs/shell/features/slash-commands

**Contents:**
- Slash commands
- Why use slash commands?
- How slash commands work
- Creating custom commands
  - Command name processing
  - Basic command format
  - Advanced command with frontmatter
    - Frontmatter fields
- Command management in Bob Shell
- Using slash commands

FeedbackCreate custom slash commands to automate workflows and standardize team practices.

To get started, type / in Bob Shell to see all available commands, or create your own by adding a markdown file to .bob/commands/ or ~/.bob/commands/.

Slash commands provide several key benefits:

When you type / in Bob Shell, a menu appears showing all available commands. These commands come from two sources:

Custom commands extend Bob's functionality by adding markdown files to specific directories:

The filename becomes the command name. For example:

When creating commands through the UI, command names are automatically processed:

Example: "My Cool Command!" becomes my-cool-command

Create a simple command by adding a markdown file:

Add metadata using frontmatter for enhanced functionality:

Bob Shell supports the same slash commands as Bob IDE. While Bob Shell does not provide a dedicated UI for managing commands, you can:

Type / in Bob Shell to see a unified menu containing the following types of commands:

Argument hints provide instant help for slash commands, showing you what kind of information to provide when a command expects additional input.

When you type / to bring up the command menu, commands that expect arguments will display a light gray hint next to them. This hint tells you what kind of argument the command is expecting.

After selecting the command, it will be inserted into the chat input followed by a space. The hint is not inserted; it is only a visual guide to help you know what to type next. You must then manually type the argument after the command.

You can add argument hints to your custom commands using the argument-hint field in the frontmatter:

This will display as /api-endpoint <endpoint-name> <http-method> in the command menu.

If your commands aren't showing up in the menu:

When a slash command isn't found, the LLM will see:

The slash menu includes mode-switching commands (like /mode code, /mode ask) that fundamentally change the AI's operational mode - they don't just inject text but switch the entire AI context. Custom modes you create also appear as slash commands (e.g., a mode with slug reviewer becomes /reviewer). These mode commands cannot be overridden by custom workflow commands.

Slash commands work identically across both Bob Shell and Bob IDE. This means:

Create automatic snapshots of your project before applying changes.

Switch between IBM instances and teams using the /instance command.

**Examples:**

Example 1 (unknown):
```unknown
.bob/commands/
├── review.md         → /review
├── test-api.md       → /test-api
└── deploy-check.md   → /deploy-check
```

Example 2 (unknown):
```unknown
Help me review this code for security issues and suggest improvements.
```

Example 3 (yaml):
```yaml
---
description: Create a new API endpoint
argument-hint: <endpoint-name> <http-method>
---
Create a new API endpoint called $1 that handles $2 requests.
Include proper error handling and documentation.
```

Example 4 (unknown):
```unknown
/mode code     Switch to Code mode
/mode ask      Switch to Ask mode
/review        Review code for security issues
/api-endpoint  <endpoint-name> <http-method>
```

---
