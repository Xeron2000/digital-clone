# Digital Clone

AI digital clone generator for Claude Code. Analyzes your conversation history to extract speaking style, thinking patterns, and vocabulary habits.

## Features

- **Universal language support** — auto-detects zh/en/ja/ko/ru/ar and mixed
- **Cross-platform** — Windows, macOS, Linux
- **Zero dependencies** — Python stdlib only
- **Incremental learning** — evolves with your conversations

## Install

```bash
npx skills add Xeron2000/digital-clone -y -g
```

## Commands

| Command | Description |
|---------|-------------|
| `/digital-clone init` | Analyze history and create profile |
| `/digital-clone chat <topic>` | Clone answers your question |
| `/digital-clone dialogue <topic>` | Two-way conversation with clone |
| `/digital-clone learn` | Update profile with new messages |
| `/digital-clone status` | Show personality stats |
| `/digital-clone export [path]` | Backup profile |

## Quick Start

```bash
# 1. Initialize your clone
/digital-clone init

# 2. Ask your clone
/digital-clone chat How should I approach learning Rust?

# 3. Have a discussion
/digital-clone dialogue Let's discuss my next project
```

## How It Works

1. Reads `~/.claude/history.jsonl` (or `%APPDATA%\claude\` on Windows)
2. Extracts 20+ communication patterns, vocabulary, and thinking style
3. Generates a personality profile at `~/.claude/digital-clone-profile.json`
4. Claude mimics your style when responding

## License

MIT
