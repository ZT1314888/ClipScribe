# Pre-Write Hook Usage Guide

## Overview

The intelligent Pre-Write Hook provides AST-level code duplication detection. Compared to traditional keyword matching:
- ✅ 80% reduction in false positives (from 50%+ down to <10%)
- ✅ Understands code structure and responsibilities
- ✅ Architecture-aware (different thresholds for different layers)
- ✅ Performance optimization and resource protection

## Quick Start

The hook is automatically enabled with no additional configuration required. Ready to use after cloning the project.

### Core Features
- **AST Structure Analysis**: Deep understanding of code structure (classes, methods, inheritance)
- **Multi-dimensional Similarity Scoring**: Comprehensive evaluation across 6 dimensions (class names, method names, imports, decorators, base classes, functions)
- **Architecture Rule Validation**: Automatic detection of layer dependency violations, singleton pattern violations, configuration access violations
- **Intelligent Search and Deduplication**: Smart search for similar code based on file roles
- **Performance Protection**: File size limits, timeout protection, resource constraints

## Configuration Files

**Hook Configuration**: `.claude/settings.json`
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/hooks/pre-write-intelligent.py",
        "timeout": 10
      }]
    }]
  }
}
```

## Custom Configuration

Edit `.claude/hooks/pre-write-intelligent.py`:

### Similarity Thresholds
```python
SIMILARITY_THRESHOLDS = {
    "service": 70,   # Service layer (strict)
    "model": 60,     # Model layer (moderate)
    "api": 50,       # API layer (loose)
    "util": 75,      # Utility classes (strict)
    "schema": 50,    # Schema (loose)
    "default": 65,   # Default
}
```

### Weight Adjustments
```python
KEYWORD_WEIGHTS = {
    "class_name": 0.25,      # Class name similarity
    "method_names": 0.20,    # Method name similarity
    "imports": 0.15,         # Import dependency similarity
    "decorators": 0.10,      # Decorator similarity
    "base_classes": 0.15,    # Inheritance relationship similarity
    "function_names": 0.15,  # Function name similarity
}
```

### Performance Configuration
```python
MAX_FILE_SIZE_MB = 5          # Maximum file size (avoid memory issues)
FIND_TIMEOUT = 5              # find command timeout (seconds)
MAX_CANDIDATE_FILES = 30      # Maximum number of candidate files to analyze
```

## Detection Logic

### Code Duplication Detection
1. **AST Parsing**: Parse code structure and extract features
2. **Role Identification**: Identify the file's role in the project (service/model/api/util/schema)
3. **Intelligent Search**: Search for files in the same layer based on role
4. **Similarity Calculation**: Multi-dimensional weighted similarity score calculation
5. **Threshold Evaluation**: Apply different thresholds based on role

### Architecture Rule Validation
1. **Layer Dependency Check**: Core/Common layers cannot import Service layer
2. **Singleton Pattern Check**: Redis, database engines can only be created in designated files
3. **Configuration Access Check**: Environment variables can only be read through `app.core.config.settings`

### Output Control
- **Critical Issues (Block Write)**:
  - Architecture rule error-level violations
  - High similarity ≥80 indicating severe duplication
- **Warnings (Allow Write but Notify)**:
  - Architecture rule warning-level violations
  - Similarity exceeds threshold but <80

## Multi-Developer Collaboration

### Scenario 1: Team Collaboration
- All developers use the same Hook configuration
- Unified code quality standards
- Shared architecture rule validation

### Scenario 2: CI/CD Environment
- Hook validation can be executed in CI
- Fast detection to ensure code quality
- Optional selective enabling/disabling of specific rules

### Scenario 3: Onboarding New Members
1. Hook automatically enabled after cloning the project
2. Refer to this documentation to understand features
3. Adjust configuration as needed

## Documentation

- **Technical Details**:
  - AST Analysis Principles: Uses Python `ast` module to parse code structure
  - Similarity Calculation Algorithm: Jaccard similarity + weighted scoring
  - Exception Handling Strategy: Timeout protection, file size limits, encoding error handling

## Frequently Asked Questions

### Q: What to do about high false positive rates?
**A**: Increase the threshold for the corresponding file role (e.g., `service: 70 → 80`)

### Q: What to do if detection is slow?
**A**:
- Reduce `MAX_CANDIDATE_FILES` (30 → 20)
- Reduce `FIND_TIMEOUT` (5 → 3)
- Exclude more directories that don't need detection

### Q: How to temporarily disable the Hook?
**A**: Comment out the PreToolUse configuration in `.claude/settings.json`

### Q: Hook errors preventing file writes?
**A**:
1. Check if Python environment is working properly
2. Review detailed error messages in stderr output
3. Temporarily disable Hook to complete urgent changes
4. Re-enable after resolving the error

## Performance Optimization Recommendations

1. **Large Projects**: Reduce `MAX_CANDIDATE_FILES` and `FIND_TIMEOUT`
2. **Small Projects**: Can increase these values for more comprehensive detection
3. **Specific Directories**: Add more exclusion rules in the `find_similar_files` function

## Support

- 📖 Project Documentation: `CLAUDE.md`
- 🤖 Architecture Consultation: `@architecture-advisor`
- 💬 Issue Feedback: Project Issues

---

**Version**: v3.0 - Stable Release
**Last Updated**: 2025-12-30
