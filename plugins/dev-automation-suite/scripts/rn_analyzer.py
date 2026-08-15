#!/usr/bin/env python3
"""
React Native Analyzer - Hybrid AST/regex code quality analyzer for React Native projects.

Covers:
  1. Component quality (hooks, props, state management)
  2. Navigation patterns (React Navigation, Expo Router)
  3. Native module compatibility checks
  4. Performance patterns (memoization, FlatList, re-renders)

Analysis modes:
  - AST mode: Uses Node.js + @babel/parser for full TS/JSX/TSX parsing
  - Regex mode: Fallback pattern matching when Node.js is unavailable

Usage:
  python rn_analyzer.py <target_file_or_directory> [--project-root <path>]

Returns: JSON report with issues, score, and recommendations
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RNIssue:
    """Single React Native quality issue."""
    severity: str          # CRITICAL, HIGH, MEDIUM, LOW
    category: str          # component, navigation, native_module, performance
    rule: str              # Machine-readable rule id
    file: str
    line: Optional[int]
    description: str
    recommendation: str


@dataclass
class RNAnalysisReport:
    """Complete React Native analysis report."""
    target: str
    analysis_mode: str     # ast | regex
    files_analyzed: int
    total_issues: int
    score: int             # 0-100
    status: str            # PASS, WARN, FAIL
    issues: list
    summary: dict
    recommendations: list


# ---------------------------------------------------------------------------
# AST helper (Node.js)
# ---------------------------------------------------------------------------

_AST_SCRIPT = r"""
// rn_ast_helper.mjs – executed by Node.js when available
// Accepts a JSON list of file paths on stdin, writes JSON analysis to stdout.

import { readFileSync } from "fs";
import { parse } from "@babel/parser";

const BABEL_OPTS = {
  sourceType: "module",
  plugins: [
    "typescript",
    "jsx",
    "decorators-legacy",
    "classProperties",
    "optionalChaining",
    "nullishCoalescingOperator",
    "exportDefaultFrom",
  ],
};

function analyzeFile(filePath) {
  const issues = [];
  let src;
  try {
    src = readFileSync(filePath, "utf-8");
  } catch {
    return issues;
  }

  let ast;
  try {
    ast = parse(src, BABEL_OPTS);
  } catch {
    return issues;
  }

  const lines = src.split("\n");

  // --- helpers -----------------------------------------------------------
  function walk(node, visitor) {
    if (!node || typeof node !== "object") return;
    if (node.type) visitor(node);
    for (const key of Object.keys(node)) {
      const child = node[key];
      if (Array.isArray(child)) child.forEach((c) => walk(c, visitor));
      else if (child && typeof child === "object" && child.type) walk(child, visitor);
    }
  }

  // Track hook call locations for rules-of-hooks lite check
  const hookCalls = [];
  let insideCondition = 0;
  let insideLoop = 0;
  let insideCallback = 0;

  walk(ast.program, (node) => {
    // -- Conditional / loop / callback depth tracking ---------------------
    if (["IfStatement", "ConditionalExpression", "SwitchStatement"].includes(node.type)) {
      insideCondition++;
      walk(node, () => {});
      insideCondition--;
      return;
    }
    if (["ForStatement", "ForInStatement", "ForOfStatement", "WhileStatement", "DoWhileStatement"].includes(node.type)) {
      insideLoop++;
      walk(node, () => {});
      insideLoop--;
      return;
    }

    // -- Hook calls -------------------------------------------------------
    if (
      node.type === "CallExpression" &&
      node.callee &&
      ((node.callee.type === "Identifier" && /^use[A-Z]/.test(node.callee.name)) ||
        (node.callee.type === "MemberExpression" &&
          node.callee.property &&
          /^use[A-Z]/.test(node.callee.property.name)))
    ) {
      const hookName = node.callee.name || node.callee.property.name;
      hookCalls.push({ name: hookName, line: node.loc?.start?.line });

      if (insideCondition > 0) {
        issues.push({
          severity: "HIGH",
          category: "component",
          rule: "hooks-conditional",
          file: filePath,
          line: node.loc?.start?.line || null,
          description: `Hook "${hookName}" called inside a conditional block.`,
          recommendation: "Move hook calls to the top level of the component to satisfy Rules of Hooks.",
        });
      }
      if (insideLoop > 0) {
        issues.push({
          severity: "HIGH",
          category: "component",
          rule: "hooks-loop",
          file: filePath,
          line: node.loc?.start?.line || null,
          description: `Hook "${hookName}" called inside a loop.`,
          recommendation: "Hooks must not be called inside loops. Refactor to call at top level.",
        });
      }

      // useEffect missing dependency array
      if (hookName === "useEffect" && node.arguments && node.arguments.length < 2) {
        issues.push({
          severity: "MEDIUM",
          category: "performance",
          rule: "useeffect-no-deps",
          file: filePath,
          line: node.loc?.start?.line || null,
          description: "useEffect called without a dependency array — runs on every render.",
          recommendation: "Add a dependency array (even empty []) to control when the effect fires.",
        });
      }
    }

    // -- Inline styles in JSX (performance) --------------------------------
    if (
      node.type === "JSXAttribute" &&
      node.name?.name === "style" &&
      node.value?.type === "JSXExpressionContainer" &&
      node.value.expression?.type === "ObjectExpression"
    ) {
      issues.push({
        severity: "LOW",
        category: "performance",
        rule: "inline-style-object",
        file: filePath,
        line: node.loc?.start?.line || null,
        description: "Inline style object creates a new reference every render.",
        recommendation: "Extract to StyleSheet.create() or a module-level constant to prevent unnecessary re-renders.",
      });
    }

    // -- Anonymous function props (performance) ----------------------------
    if (
      node.type === "JSXAttribute" &&
      node.value?.type === "JSXExpressionContainer" &&
      ["ArrowFunctionExpression", "FunctionExpression"].includes(node.value.expression?.type) &&
      node.name?.name?.startsWith("on")
    ) {
      issues.push({
        severity: "LOW",
        category: "performance",
        rule: "anonymous-handler-prop",
        file: filePath,
        line: node.loc?.start?.line || null,
        description: `Anonymous function passed to "${node.name.name}" prop — new reference every render.`,
        recommendation: "Extract handler to useCallback or a named function to stabilise the reference.",
      });
    }

    // -- FlatList without keyExtractor ------------------------------------
    if (
      node.type === "JSXOpeningElement" &&
      node.name?.name === "FlatList"
    ) {
      const hasKeyExtractor = (node.attributes || []).some(
        (a) => a.type === "JSXAttribute" && a.name?.name === "keyExtractor"
      );
      if (!hasKeyExtractor) {
        issues.push({
          severity: "MEDIUM",
          category: "performance",
          rule: "flatlist-no-keyextractor",
          file: filePath,
          line: node.loc?.start?.line || null,
          description: "FlatList rendered without a keyExtractor prop.",
          recommendation: "Provide a keyExtractor for stable item identity and efficient list diffing.",
        });
      }
      // Check for missing getItemLayout
      const hasGetItemLayout = (node.attributes || []).some(
        (a) => a.type === "JSXAttribute" && a.name?.name === "getItemLayout"
      );
      const hasRenderItem = (node.attributes || []).some(
        (a) => a.type === "JSXAttribute" && a.name?.name === "renderItem"
      );
      if (hasRenderItem && !hasGetItemLayout) {
        issues.push({
          severity: "LOW",
          category: "performance",
          rule: "flatlist-no-getitemlayout",
          file: filePath,
          line: node.loc?.start?.line || null,
          description: "FlatList without getItemLayout may cause scroll-position jumps.",
          recommendation: "When item height is fixed, provide getItemLayout for faster rendering.",
        });
      }
    }
  });

  return issues;
}

// Main
const input = readFileSync(0, "utf-8");
const files = JSON.parse(input);
const allIssues = [];
for (const f of files) {
  allIssues.push(...analyzeFile(f));
}
process.stdout.write(JSON.stringify(allIssues));
"""


def _node_available() -> bool:
    """Return True if Node.js >= 18 is available."""
    try:
        result = subprocess.run(
            ["node", "-e", "process.stdout.write(String(process.versions.node))"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            major = int(result.stdout.strip().split(".")[0])
            return major >= 18
    except Exception:
        pass
    return False


def _babel_available() -> bool:
    """Return True if @babel/parser can be resolved by Node."""
    try:
        result = subprocess.run(
            ["node", "-e", "require.resolve('@babel/parser')"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _install_babel() -> bool:
    """Attempt to install @babel/parser globally."""
    try:
        result = subprocess.run(
            ["npm", "install", "-g", "@babel/parser"],
            capture_output=True, text=True, timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def run_ast_analysis(files: list[str]) -> list[dict]:
    """Run the Node.js AST analysis script on the given files."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".mjs", delete=False) as tmp:
        tmp.write(_AST_SCRIPT)
        tmp.flush()
        script_path = tmp.name

    try:
        proc = subprocess.run(
            ["node", script_path],
            input=json.dumps(files),
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
    except Exception:
        pass
    finally:
        os.unlink(script_path)

    return []


# ---------------------------------------------------------------------------
# Regex fallback analysis
# ---------------------------------------------------------------------------

# Compiled patterns
_RE_HOOK_CALL = re.compile(r"\b(use[A-Z]\w*)\s*\(")
_RE_USEEFFECT_NO_DEPS = re.compile(r"useEffect\s*\(\s*(?:async\s*)?\(?\)?\s*=>\s*\{")
_RE_USEEFFECT_WITH_DEPS = re.compile(r"useEffect\s*\([^)]*,\s*\[")
_RE_INLINE_STYLE = re.compile(r"style\s*=\s*\{\s*\{")
_RE_ANON_HANDLER = re.compile(r"on[A-Z]\w*\s*=\s*\{\s*\(?[^)]*\)?\s*=>")
_RE_FLATLIST = re.compile(r"<\s*FlatList\b")
_RE_KEY_EXTRACTOR = re.compile(r"keyExtractor\s*=")
_RE_GET_ITEM_LAYOUT = re.compile(r"getItemLayout\s*=")
_RE_MEMO = re.compile(r"\bReact\.memo\b|\bmemo\(")
_RE_USECALLBACK = re.compile(r"\buseCallback\b")
_RE_USEMEMO = re.compile(r"\buseMemo\b")
_RE_NAVIGATION_IMPORT = re.compile(
    r"from\s+['\"]@react-navigation/|from\s+['\"]expo-router['\"]"
)
_RE_NATIVEMODULES = re.compile(r"\bNativeModules\b|\brequireNativeComponent\b")
_RE_LINKING = re.compile(r"from\s+['\"]react-native/Libraries/Linking")
_RE_PLATFORM_SELECT = re.compile(r"Platform\.select\b|Platform\.OS\b")
_RE_STYLESHEET = re.compile(r"StyleSheet\.create\b")
_RE_CONDITIONAL_HOOK = re.compile(
    r"(?:if\s*\(|&&\s*|:\s*|\?\s*)[^;{]*\buse[A-Z]\w*\s*\("
)
_RE_EXPO_ROUTER_TABS = re.compile(r"from\s+['\"]expo-router['\"].*Tabs|<\s*Tabs\b")
_RE_EXPO_ROUTER_STACK = re.compile(r"from\s+['\"]expo-router['\"].*Stack|<\s*Stack\b")
_RE_SCREEN_OPTIONS = re.compile(r"screenOptions\s*=|options\s*=")
_RE_NAVIGATION_TYPED = re.compile(
    r"useNavigation<|useRoute<|NativeStackNavigationProp|RouteProp<"
)
_RE_TURBO_MODULE = re.compile(r"TurboModuleRegistry|TurboModule")
_RE_NATIVE_WIND = re.compile(r"className\s*=")
_RE_REQUIRE_NATIVE = re.compile(r"requireNativeComponent\s*[<(]")


def _regex_analyze_file(file_path: str) -> list[dict]:
    """Analyze a single file using regex patterns."""
    issues: list[dict] = []
    try:
        with open(file_path, "r", errors="replace") as fh:
            content = fh.read()
            lines = content.split("\n")
    except Exception:
        return issues

    def _add(severity, category, rule, line, desc, rec):
        issues.append({
            "severity": severity,
            "category": category,
            "rule": rule,
            "file": file_path,
            "line": line,
            "description": desc,
            "recommendation": rec,
        })

    for idx, line_text in enumerate(lines, start=1):
        # Hooks in conditionals
        if _RE_CONDITIONAL_HOOK.search(line_text):
            _add("HIGH", "component", "hooks-conditional", idx,
                 "Possible hook call inside a conditional expression.",
                 "Move hook calls to the top level of the component to satisfy Rules of Hooks.")

        # Inline style objects
        if _RE_INLINE_STYLE.search(line_text):
            _add("LOW", "performance", "inline-style-object", idx,
                 "Inline style object creates a new reference every render.",
                 "Extract to StyleSheet.create() or a module-level constant.")

        # Anonymous handler props
        if _RE_ANON_HANDLER.search(line_text):
            _add("LOW", "performance", "anonymous-handler-prop", idx,
                 "Anonymous arrow function in event handler prop — new reference every render.",
                 "Extract to useCallback or a named function.")

    # useEffect without dependency array
    effect_no_deps = set()
    for m in _RE_USEEFFECT_NO_DEPS.finditer(content):
        effect_no_deps.add(content[:m.start()].count("\n") + 1)
    for m in _RE_USEEFFECT_WITH_DEPS.finditer(content):
        line_num = content[:m.start()].count("\n") + 1
        effect_no_deps.discard(line_num)
    for ln in effect_no_deps:
        # Double-check it's not followed by a dep array on next lines
        _add("MEDIUM", "performance", "useeffect-no-deps", ln,
             "useEffect without a dependency array — runs on every render.",
             "Add a dependency array (even empty []) to control when the effect fires.")

    # FlatList checks
    for m in _RE_FLATLIST.finditer(content):
        start = m.start()
        # Grab a ~600 char window after <FlatList to find closing >
        window = content[start:start + 600]
        line_num = content[:start].count("\n") + 1
        if not _RE_KEY_EXTRACTOR.search(window):
            _add("MEDIUM", "performance", "flatlist-no-keyextractor", line_num,
                 "FlatList rendered without a keyExtractor prop.",
                 "Provide keyExtractor for stable item identity and efficient list diffing.")
        if not _RE_GET_ITEM_LAYOUT.search(window):
            _add("LOW", "performance", "flatlist-no-getitemlayout", line_num,
                 "FlatList without getItemLayout may cause scroll-position jumps.",
                 "When item height is fixed, provide getItemLayout for faster rendering.")

    # Navigation: untyped useNavigation / useRoute (TypeScript projects)
    if file_path.endswith((".ts", ".tsx")):
        if _RE_NAVIGATION_IMPORT.search(content):
            has_typed = _RE_NAVIGATION_TYPED.search(content)
            if not has_typed:
                nav_calls = re.findall(r"\buseNavigation\b|\buseRoute\b", content)
                if nav_calls:
                    _add("MEDIUM", "navigation", "untyped-navigation-hooks", None,
                         "useNavigation/useRoute called without TypeScript generic type parameter.",
                         "Type navigation hooks for compile-time route safety: useNavigation<StackNavProp>().")

    # Native module checks
    if _RE_NATIVEMODULES.search(content) and not _RE_PLATFORM_SELECT.search(content):
        _add("MEDIUM", "native_module", "native-no-platform-check", None,
             "NativeModules or requireNativeComponent used without Platform.OS/Platform.select guard.",
             "Wrap native module access in Platform checks to prevent crashes on unsupported platforms.")

    # TurboModule usage without Platform guard
    if _RE_TURBO_MODULE.search(content) and not _RE_PLATFORM_SELECT.search(content):
        _add("LOW", "native_module", "turbo-module-no-platform", None,
             "TurboModuleRegistry reference without explicit Platform guard.",
             "Guard TurboModule lookups with Platform.OS checks for cross-platform safety.")

    return issues


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

_RN_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs"}
_IGNORE_DIRS = {"node_modules", ".expo", ".git", "android", "ios", "__tests__", "dist", "build"}


def discover_rn_files(target: str) -> list[str]:
    """Discover React Native source files under target path."""
    target_path = Path(target)
    if target_path.is_file():
        return [str(target_path)] if target_path.suffix in _RN_EXTENSIONS else []

    files = []
    for root, dirs, filenames in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in filenames:
            fpath = Path(root) / fname
            if fpath.suffix in _RN_EXTENSIONS:
                files.append(str(fpath))
    return sorted(files)


# ---------------------------------------------------------------------------
# Scoring and status
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHTS = {"CRITICAL": 15, "HIGH": 8, "MEDIUM": 3, "LOW": 1}


def calculate_score(issues: list[dict]) -> int:
    """Calculate quality score 0-100 based on issues found."""
    deductions = sum(_SEVERITY_WEIGHTS.get(i["severity"], 3) for i in issues)
    return max(0, 100 - deductions)


def determine_status(score: int) -> str:
    if score >= 90:
        return "PASS"
    elif score >= 70:
        return "WARN"
    return "FAIL"


def build_summary(issues: list[dict]) -> dict:
    by_severity = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    by_category = {"component": 0, "navigation": 0, "native_module": 0, "performance": 0}
    by_rule: dict[str, int] = {}
    for issue in issues:
        by_severity[issue["severity"]] = by_severity.get(issue["severity"], 0) + 1
        by_category[issue["category"]] = by_category.get(issue["category"], 0) + 1
        by_rule[issue["rule"]] = by_rule.get(issue["rule"], 0) + 1
    return {"by_severity": by_severity, "by_category": by_category, "by_rule": by_rule}


def build_recommendations(issues: list[dict]) -> list[str]:
    recs: list[str] = []
    rules_seen = set()
    for issue in issues:
        if issue["rule"] not in rules_seen:
            rules_seen.add(issue["rule"])
            recs.append(issue["recommendation"])
    if not recs:
        recs.append("All React Native quality checks passed.")
    return recs


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

def analyze(target: str, project_root: Optional[str] = None) -> RNAnalysisReport:
    """Run full React Native analysis on target file or directory."""
    files = discover_rn_files(target)
    if not files:
        return RNAnalysisReport(
            target=target,
            analysis_mode="none",
            files_analyzed=0,
            total_issues=0,
            score=100,
            status="PASS",
            issues=[],
            summary=build_summary([]),
            recommendations=["No React Native source files found to analyze."],
        )

    # Determine analysis mode
    use_ast = False
    mode = "regex"
    if _node_available():
        if _babel_available():
            use_ast = True
            mode = "ast"
        else:
            if _install_babel():
                use_ast = True
                mode = "ast"
            else:
                mode = "regex"

    all_issues: list[dict] = []
    if use_ast:
        ast_issues = run_ast_analysis(files)
        all_issues.extend(ast_issues)
    else:
        for fpath in files:
            all_issues.extend(_regex_analyze_file(fpath))

    # Regex-only rules run regardless (navigation typing, native module guards)
    # are already covered in regex path; for AST path we supplement:
    if use_ast:
        for fpath in files:
            supplemental = _regex_analyze_file(fpath)
            # Only add rules not already covered by AST
            ast_rules = {(i["file"], i["line"], i["rule"]) for i in all_issues}
            for si in supplemental:
                key = (si["file"], si["line"], si["rule"])
                if key not in ast_rules:
                    all_issues.append(si)

    # Deduplicate
    seen = set()
    deduped = []
    for issue in all_issues:
        key = (issue["file"], issue.get("line"), issue["rule"])
        if key not in seen:
            seen.add(key)
            deduped.append(issue)

    score = calculate_score(deduped)
    status = determine_status(score)
    summary = build_summary(deduped)
    recs = build_recommendations(deduped)

    return RNAnalysisReport(
        target=target,
        analysis_mode=mode,
        files_analyzed=len(files),
        total_issues=len(deduped),
        score=score,
        status=status,
        issues=deduped,
        summary=summary,
        recommendations=recs,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="React Native Code Quality Analyzer")
    parser.add_argument("target", help="File or directory to analyze")
    parser.add_argument("--project-root", dest="project_root", default=None,
                        help="Project root directory (for import resolution)")
    args = parser.parse_args()

    report = analyze(args.target, args.project_root)
    print(json.dumps(asdict(report), indent=2))

    if report.status == "FAIL":
        sys.exit(1)
    elif report.status == "WARN":
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
