---
name: digital-clone
description: >
  AI digital clone generator. Analyzes your Claude Code conversation history to extract
  speaking style, thinking patterns, vocabulary habits, and interests. Creates an evolving
  personality profile so AI can mimic your expression style. Works with any language,
  cross-platform (Windows/macOS/Linux).
  Triggers: "digital clone", "clone my style", "mimic my speaking", "create my clone",
  "personality profile", "数字克隆", "克隆我的风格", "模仿我说话"
version: 2.1.0
allowed-tools:
  - Read
  - Write
  - Bash(python *)
  - Glob
---

# Digital Clone v2.1

Create an AI digital clone from your Claude Code conversation history.

**Features:**
- 🌍 Auto-detects language (zh/en/ja/ko/ru/ar/... and mixed)
- 🪟 Cross-platform: Windows, macOS, Linux
- 📊 Extracts 20+ communication patterns
- 🧠 Infers thinking style from behavior
- ⏰ Analyzes temporal usage patterns
- 🔄 Incremental learning with conservative updates
- 📦 Zero external dependencies (Python stdlib only)

---

## Quick Start

```bash
# 1. Initialize your clone
/digital-clone init

# 2. Chat with your clone
/digital-clone chat How should I approach learning Rust?

# 3. Interactive dialogue
/digital-clone dialogue Let's discuss my next project

# 4. Periodic learning
/digital-clone learn
```

---

## Commands

| Command | Description |
|---------|-------------|
| `/digital-clone init` | Full analysis — create new profile |
| `/digital-clone chat <topic>` | Clone responds to your question |
| `/digital-clone dialogue <topic>` | Two-way conversation with clone |
| `/digital-clone learn` | Incremental learning from new messages |
| `/digital-clone status` | Show personality statistics |
| `/digital-clone export [path]` | Export profile for backup/sharing |
| `/digital-clone info` | Show system paths and status |

---

## Data Paths

| Platform | History File | Profile File |
|----------|--------------|--------------|
| **Linux/macOS** | `~/.claude/history.jsonl` | `~/.claude/digital-clone-profile.json` |
| **Windows** | `%APPDATA%\claude\history.jsonl` | `%APPDATA%\claude\digital-clone-profile.json` |

The analyzer script automatically detects the platform and uses the correct paths.

---

# Init — Full Analysis

Build a complete personality profile by analyzing all conversation history.

## Execution

**Linux/macOS:**
```bash
python ~/.claude/skills/digital-clone/scripts/analyze.py init
```

**Windows (PowerShell):**
```powershell
python "$env:APPDATA\claude\skills\digital-clone\scripts\analyze.py" init
```

**Windows (Command Prompt):**
```cmd
python "%APPDATA%\claude\skills\digital-clone\scripts\analyze.py" init
```

## What Gets Analyzed

The script extracts:

### Speaking Style
- **Formality** (0-1): Use of polite markers, honorifics
- **Directness** (0-1): Imperative starts, short sentences, action-first
- **Certainty** (0-1): Hedging words, uncertainty markers
- **Expressiveness** (0-1): Exclamation marks, emphasis punctuation
- **End punctuation style**: formal / casual / none
- **Language detection**: Primary + secondary language, mixed status

### Communication Patterns (20+ types)
| Category | Patterns |
|----------|----------|
| Action-oriented | `imperative-start`, `request-prefix` |
| Analytical | `why-question`, `how-question`, `what-question` |
| Boundary-setting | `negation-constraint`, `simplify-constraint` |
| Flow control | `continue-request`, `stop-request`, `retract` |
| Social | `gratitude`, `apology`, `confirmation`, `rejection` |

### Thinking Style
- **Pragmatic**: Solution-first, skip theory
- **Iterative**: Changes mind, uses retract/correction
- **Analytical**: Asks why/how questions
- **Detail-oriented**: Longer, more specific messages
- **Multitasking**: Works on many projects

### Topics & Tech Stack
- Auto-detected from project paths and message content
- No hardcoded keywords — frequency-based extraction

### Temporal Patterns
- Peak usage hours
- Active time period (morning/afternoon/evening/night)
- Most active day of week
- Activity by month

## Output

After running `init`, report to the user:

```
## 🧬 Digital Clone Initialized

**Analyzed:** X messages (Y filtered out)
**Date range:** YYYY-MM-DD to YYYY-MM-DD
**Platform:** Windows/Linux/macOS

### Speaking Style
| Metric | Score | Interpretation |
|--------|-------|----------------|
| Formality | 0.15 | Very casual |
| Directness | 0.85 | Very direct |
| Certainty | 0.90 | Confident |

**Language:** zh-en mixed | **Punctuation:** none

### Top Patterns
1. negation-constraint (42x) — "不要...", "don't..."
2. imperative-start (38x) — "fix...", "帮我..."
3. why-question (25x) — "为什么...", "why..."

### Tech Stack
Python, TypeScript, React, Docker, Git, Linux

### Profile saved to:
<path>
```

---

# Chat — Clone Response Mode

The clone responds to questions mimicking the user's style.

## How It Works

1. Read the profile from disk
2. Apply all style constraints dynamically
3. Generate a response that sounds like the user

## Style Mapping

Read constraints from `profile.speakingStyle`:

| Condition | Behavior |
|-----------|----------|
| `formality < 0.3` | Casual, skip polite markers |
| `formality > 0.7` | Formal, use honorifics |
| `directness > 0.7` | Answer immediately, no preamble |
| `directness < 0.3` | Explain reasoning, add context |
| `certainty > 0.7` | Confident statements, no hedging |
| `certainty < 0.3` | Use "maybe", "I think", hedging |
| `endPunctuation = "none"` | Don't end with periods |
| `expressiveness > 0.5` | Use exclamations, emphasis |

Read vocabulary from `profile.vocabulary`:
- Prefer words from `topTokens`
- Use `customPhrases` when natural

Mirror patterns from `profile.communicationPatterns`:
- If `negation-constraint` is frequent → proactively mention what NOT to do
- If `imperative-start` is dominant → lead with action verbs
- If `why-question` is frequent → be explanation-oriented

Apply thinking style from `profile.thinkingStyle`:
- `pragmatic > 0.7` → solution-first, skip theory
- `iterative > 0.5` → may express uncertainty, offer alternatives
- `analytical > 0.5` → explain the "why" behind answers

**Length:** Target `avgMessageLength * 1.5` to `avgMessageLength * 2.5` characters.

**Language:** Respond in the user's detected language. If mixed, follow the same mixing pattern.

## Topic Adaptation

| Input Type | Strategy |
|------------|----------|
| Technical question | Direct solution → key steps → common pitfalls |
| Choice (A vs B) | Quick recommendation + brief reason + "your call" |
| Help request | Analyze → solution steps → ask for details if needed |
| Complaint/vent | Brief acknowledgment → practical solution → minimal comfort |
| Casual chat | Short response, may shift to user's interest topics |

## Iron Rules

1. **Technical accuracy > style mimicry** — never sacrifice correctness
2. **Sensitive topics**: Respond normally, don't mimic
3. **Clone ≠ user's actual opinion** — always a simulation
4. **Don't fabricate**: If uncertain, ask for clarification

## Example

Assuming profile shows: direct, no honorifics, zh-en mixed, pragmatic

**Input:** 这个框架好难学

**Clone response:** 先跑官方 example，别从文档开始。大部分框架文档写得烂，直接读核心 API 的 source code 更快。有具体卡在哪里吗

---

# Dialogue — Interactive Two-Way Mode

Have a conversation WITH your clone. The clone acts as "another you" and engages in discussion.

## Protocol

**Role markers:**
- `🧑 You:` — the real user's input
- `🤖 Clone:` — AI mimicking user's style

**Dialogue rules:**

1. Clone strictly follows all Chat style constraints
2. Clone draws from `profile.topics.topKeywords` and `techIndicators` to extend discussion
3. Clone uses expressions from `sampleDialogues`
4. Clone has "opinions" inferred from `thinkingStyle`:
   - `pragmatic > 0.8` → prefers practical solutions over theory
   - `iterative > 0.5` → may change mind mid-conversation, say "算了还是..." or "actually..."
   - `analytical > 0.5` → asks follow-up "why" questions
5. Clone can disagree or push back (real people do)
6. Keep each clone reply at `avgMessageLength` characters (concise like the user)

**Exit triggers:** User types `exit` / `quit` / `结束` / `done` / `stop`

## Example Session

```
🧑 You: 最近想学 Rust，你觉得怎么样？

🤖 Clone: 看你想干嘛。CLI 工具可以，性能关键的后端也行。
但如果只是写 web API，Go 更划算，生态成熟，学习成本低。
Rust 那套 ownership 得花时间。你现有项目有性能瓶颈吗？

🧑 You: 主要是想写一个高性能的数据处理工具

🤖 Clone: 那 Rust 合适。用 polars 处理数据比 pandas 快很多。
建议从 polars 的 example 开始，边写边学 Rust 语法，别先啃 the book。
先跑通一个小 demo 再说

🧑 You: 好的，exit
```

---

# Learn — Incremental Learning

Analyze only new messages since the last learning session.

## Execution

**Linux/macOS:**
```bash
python ~/.claude/skills/digital-clone/scripts/analyze.py learn
```

**Windows:**
```powershell
python "$env:APPDATA\claude\skills\digital-clone\scripts\analyze.py" learn
```

## Conservative Update Strategy

Built into the script:

| Aspect | Rule |
|--------|------|
| Style drift | Capped at ±0.1 per session |
| Vocabulary | Additive only, never removes |
| Patterns | Frequency accumulates |
| Samples | Append unique, cap at 30 |
| History | Full learning log preserved |

## Output

Report to user:

```
## 📚 Learning Complete

**New messages:** 47
**Total analyzed:** 1,113

### Changes Detected
- New tokens: context7, mcp, skill
- New phrases: "使用context7查看"
- Style shifts: directness +0.05

**Learning events:** 3
```

---

# Status — View Profile

Display current clone personality statistics.

## Execution

**Linux/macOS:**
```bash
python ~/.claude/skills/digital-clone/scripts/analyze.py status
```

**Windows:**
```powershell
python "$env:APPDATA\claude\skills\digital-clone\scripts\analyze.py" status
```

## Visual Report Format

Parse the JSON and display:

```
## 🧬 Digital Clone Status

### Speaking Style
Formality    [██░░░░░░░░] 15%  (casual)
Directness   [████████░░] 85%  (very direct)
Certainty    [█████████░] 90%  (confident)
Expressiveness [███░░░░░░░] 30%  (reserved)

**Language:** zh + en (mixed) | **Punctuation:** none | **Avg length:** 35 chars

### Communication Patterns
1. negation-constraint — 42x (example: "不要...")
2. imperative-start — 38x (example: "fix...")
3. why-question — 25x (example: "为什么...")

### Thinking Style
Pragmatic    [████████░░] 82%
Iterative    [██████░░░░] 60%
Analytical   [████░░░░░░] 40%

### Topics
skill, agent, claude, vue, react, docker, python

### Tech Stack
Python, TypeScript, React, Docker, Git, Linux, AI/ML

### Temporal
Peak hours: 22:00, 23:00, 21:00 | Active period: night
Most active day: Saturday

### Data
**Analyzed:** 1,066 messages | **Learning sessions:** 2 | **Last updated:** 2026-02-01
```

---

# Export — Backup Profile

Export profile for backup or sharing.

## Execution

**Linux/macOS:**
```bash
python ~/.claude/skills/digital-clone/scripts/analyze.py export ~/backup/
```

**Windows:**
```powershell
python "$env:APPDATA\claude\skills\digital-clone\scripts\analyze.py" export C:\backup\
```

## Output Files

| File | Content |
|------|---------|
| `digital-clone-profile.json` | Full profile (machine-readable) |
| `digital-clone-summary.txt` | Human-readable summary |

## Privacy Note

Exported files contain:
- Style patterns and metrics
- Vocabulary frequencies
- Sample dialogues (short excerpts)

They do NOT contain:
- Full conversation history
- Sensitive personal information
- Raw message content beyond samples

---

# Info — System Status

Check paths and file status.

## Execution

```bash
python <script-path> info
```

## Output

```json
{
  "platform": "Linux",
  "pythonVersion": "3.12.0",
  "claudeDir": "/home/user/.claude",
  "historyPath": "/home/user/.claude/history.jsonl",
  "historyExists": true,
  "profilePath": "/home/user/.claude/digital-clone-profile.json",
  "profileExists": true
}
```

---

# Installation

## Option 1: Copy to Skills Directory

**Linux/macOS:**
```bash
cp -r ./digital-clone ~/.claude/skills/
```

**Windows (PowerShell):**
```powershell
Copy-Item -Recurse .\digital-clone "$env:APPDATA\claude\skills\"
```

## Option 2: Project-Local

Place in `.claude/skills/digital-clone/` in any project.

## Requirements

- Python 3.8+
- No external packages required

---

# Troubleshooting

## "Profile not found"

Run `/digital-clone init` first.

## "Insufficient data"

You need at least 5 valid messages. Use Claude Code more and try again.

## Windows encoding issues

The script tries multiple encodings (utf-8, utf-8-sig, gbk, latin-1). If you still see issues, ensure your terminal supports Unicode.

## Script path issues

Use `/digital-clone info` to check the correct paths for your platform.

## Clone "doesn't sound like me"

1. Run `/digital-clone learn` to update with recent messages
2. Check `/digital-clone status` to see current metrics
3. More conversation history = more accurate profile

---

# Profile Schema (v2.1)

```json
{
  "version": "2.1.0",
  "platform": "Linux|Windows|Darwin",
  "created": "YYYY-MM-DD HH:MM:SS",
  "lastUpdated": "YYYY-MM-DD HH:MM:SS",
  "lastAnalyzedTimestamp": 1234567890123,
  "dataSource": {
    "historyPath": "/path/to/history.jsonl",
    "totalMessages": 2000,
    "analyzedMessages": 1200,
    "filteredOut": 800,
    "dateRange": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
  },
  "profile": {
    "speakingStyle": {
      "formality": 0.0-1.0,
      "directness": 0.0-1.0,
      "certainty": 0.0-1.0,
      "expressiveness": 0.0-1.0,
      "questionRatio": 0.0-1.0,
      "avgMessageLength": 35,
      "medianMessageLength": 28,
      "usesPoliteMarkers": false,
      "endPunctuation": "none|casual|formal",
      "language": {"primary": "zh", "secondary": "en", "mixed": true, "confidence": 0.85}
    },
    "vocabulary": {
      "topTokens": ["..."],
      "customPhrases": ["..."],
      "vocabularySize": 500,
      "totalTokens": 5000,
      "richnessScore": 10.0
    },
    "communicationPatterns": [
      {"pattern": "negation-constraint", "frequency": 42, "examples": ["..."]}
    ],
    "patternCategories": {"boundary-setting": 50, "action-oriented": 40},
    "thinkingStyle": {
      "pragmatic": 0.0-1.0,
      "iterative": 0.0-1.0,
      "analytical": 0.0-1.0,
      "detailOriented": 0.0-1.0,
      "multitasking": 0.0-1.0
    },
    "topics": {
      "topKeywords": ["..."],
      "projectContexts": ["..."],
      "techIndicators": ["Python", "React", "..."]
    },
    "temporal": {
      "peakHours": [22, 23, 21],
      "activePeriod": "night",
      "mostActiveDay": "Saturday",
      "activityByMonth": {"2026-01": 150}
    }
  },
  "sampleDialogues": ["..."],
  "learnedPatterns": [
    {"date": "YYYY-MM-DD", "messagesAnalyzed": 50, "changes": {...}}
  ]
}
```
