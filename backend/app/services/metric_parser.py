"""
Restricted Arithmetic Metric Expression Parser and SQL Compiler.

Design & Security Specifications:
1. Restricted Grammar:
   - Supports ONLY basic arithmetic (+, -, *, /), unary (+, -), and parentheses ( ).
   - Accepts numeric constants (integers and floating-point values).
   - Validates all column identifiers against authorized schema columns.
   - Absolutely NO function calls, variable assignments, dunders, or arbitrary SQL fragments.

2. Spaced & Quoted Column Names:
   - Accepts unquoted spaced column names (e.g. Unit Price * Quantity Ordered).
   - Accepts backtick-quoted identifiers (e.g. `Unit Price` * `Quantity Ordered`).
   - Accepts bracket-quoted identifiers (e.g. [Unit Price] * [Quantity Ordered]).
   - Resolves case-insensitively and maps to canonical schema column names.

3. Division-by-Zero & Null Semantics:
   - All division operations are compiled using `NULLIF(denominator, 0)`.
   - In SQL, division by NULL yields NULL rather than a runtime error (e.g. 100 / 0 -> NULL).
   - Standard SQL NULL propagation applies to arithmetic operations (NULL + X = NULL).
"""

import re
from typing import List, Tuple, Any, Optional


class ExpressionNode:
    """Base node for restricted arithmetic expression AST."""
    def to_sql(self) -> str:
        raise NotImplementedError


class NumberNode(ExpressionNode):
    """Represents a numeric constant."""
    def __init__(self, value: float):
        self.value = value

    def to_sql(self) -> str:
        if self.value.is_integer():
            return str(int(self.value))
        return str(self.value)


class ColumnNode(ExpressionNode):
    """Represents an authorized dataset column reference."""
    def __init__(self, column: str):
        self.column = column

    def to_sql(self) -> str:
        return f"`{self.column}`"


class UnaryOpNode(ExpressionNode):
    """Represents a unary operation (+ or -)."""
    def __init__(self, op: str, operand: ExpressionNode):
        self.op = op
        self.operand = operand

    def to_sql(self) -> str:
        return f"({self.op}{self.operand.to_sql()})"


class BinaryOpNode(ExpressionNode):
    """Represents a binary arithmetic operation (+, -, *, /)."""
    def __init__(self, op: str, left: ExpressionNode, right: ExpressionNode):
        self.op = op
        self.left = left
        self.right = right

    def to_sql(self) -> str:
        left_sql = self.left.to_sql()
        right_sql = self.right.to_sql()
        if self.op == "/":
            # Guard against division by zero in SQL by using NULLIF(denominator, 0)
            return f"({left_sql} / NULLIF({right_sql}, 0))"
        return f"({left_sql} {self.op} {right_sql})"


def tokenize_expression(expr: str, allowed_columns: List[str]) -> List[Tuple[str, Any]]:
    """
    Tokenizes a metric expression into typed tokens.
    Rejects forbidden characters and validates column names against allowed schema.
    """
    col_map = {}
    for c in allowed_columns:
        col_map[c.lower()] = c
        col_map[c.lower().replace("_", " ")] = c
        col_map[c.lower().replace(" ", "_")] = c

    # Sort columns by length descending to match longest column names first
    sorted_cols = sorted(allowed_columns, key=len, reverse=True)

    tokens = []
    i = 0
    n = len(expr)

    while i < n:
        c = expr[i]

        if c.isspace():
            i += 1
            continue

        if c in ("+", "-", "*", "/"):
            tokens.append(("OP", c))
            i += 1
            continue

        if c == "(":
            tokens.append(("LPAREN", "("))
            i += 1
            continue

        if c == ")":
            tokens.append(("RPAREN", ")"))
            i += 1
            continue

        # Dangerous SQL injection / comment / statement separator characters
        if c == ";" or expr[i:i+2] in ("--", "/*", "*/"):
            raise ValueError("Expression contains invalid characters or SQL comments.")

        # Quoted identifiers: `...` or [...] or "..."
        if c in ("`", "[", '"'):
            quote_end = "`" if c == "`" else ("]" if c == "[" else '"')
            end_idx = expr.find(quote_end, i + 1)
            if end_idx == -1:
                raise ValueError(f"Unclosed quote in expression: {expr[i:]}")
            raw_name = expr[i+1:end_idx].strip()
            if raw_name.lower() not in col_map:
                allowed_str = ", ".join(sorted(allowed_columns))
                raise ValueError(f"Column '{raw_name}' in expression does not exist in dataset schema. Allowed columns: {allowed_str}")
            tokens.append(("COLUMN", col_map[raw_name.lower()]))
            i = end_idx + 1
            continue

        # Numbers
        num_match = re.match(r"^\d+(\.\d+)?", expr[i:])
        if num_match:
            val_str = num_match.group(0)
            tokens.append(("NUMBER", float(val_str)))
            i += len(val_str)
            continue

        # Check for known allowed column starting at index i (unquoted)
        matched_col = None
        for col in sorted_cols:
            col_len = len(col)
            candidate = expr[i:i+col_len]
            if candidate.lower() in (col.lower(), col.lower().replace("_", " "), col.lower().replace(" ", "_")):
                # Check word boundary: next char cannot be alphanumeric or underscore
                next_char = expr[i+col_len] if i+col_len < n else ""
                if not next_char or not (next_char.isalnum() or next_char == "_"):
                    matched_col = col_map[candidate.lower()]
                    i += col_len
                    break

        if matched_col:
            tokens.append(("COLUMN", matched_col))
            continue

        # Non-matching identifier word/phrase up to next operator/paren/end
        ident_match = re.match(r"^[a-zA-Z_][a-zA-Z0-9_\s]*?(?=[+\-*/\(\)]|$)", expr[i:])
        if ident_match:
            raw_ident = ident_match.group(0).strip()
            if raw_ident.lower() in col_map:
                tokens.append(("COLUMN", col_map[raw_ident.lower()]))
            else:
                allowed_str = ", ".join(sorted(allowed_columns))
                raise ValueError(f"Column '{raw_ident}' in expression does not exist in dataset schema. Allowed columns: {allowed_str}")
            i += len(ident_match.group(0))
            continue

        raise ValueError(f"Unexpected character in expression at position {i}: '{c}'")

    return tokens


class ExpressionParser:
    """
    Recursive-descent parser for restricted arithmetic expressions:
    expr   -> term (('+' | '-') term)*
    term   -> factor (('*' | '/') factor)*
    factor -> ('+' | '-') factor | atom
    atom   -> NUMBER | COLUMN | '(' expr ')'
    """
    def __init__(self, tokens: List[Tuple[str, Any]]):
        self.tokens = tokens
        self.pos = 0
        self.referenced_columns: List[str] = []

    def current(self) -> Tuple[str, Any]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return ("EOF", None)

    def eat(self, token_type: str, value: Optional[str] = None) -> Tuple[str, Any]:
        tok = self.current()
        if tok[0] != token_type or (value is not None and tok[1] != value):
            raise ValueError(f"Syntax error: expected {token_type} {value or ''}, got {tok[0]} '{tok[1]}'")
        self.pos += 1
        return tok

    def parse(self) -> ExpressionNode:
        if not self.tokens:
            raise ValueError("Expression is empty.")
        node = self.expr()
        if self.pos < len(self.tokens):
            extra = self.tokens[self.pos]
            raise ValueError(f"Unexpected token after expression: {extra[1]}")
        return node

    def expr(self) -> ExpressionNode:
        node = self.term()
        while self.current()[0] == "OP" and self.current()[1] in ("+", "-"):
            op = self.eat("OP")[1]
            right = self.term()
            node = BinaryOpNode(op, node, right)
        return node

    def term(self) -> ExpressionNode:
        node = self.factor()
        while self.current()[0] == "OP" and self.current()[1] in ("*", "/"):
            op = self.eat("OP")[1]
            right = self.factor()
            node = BinaryOpNode(op, node, right)
        return node

    def factor(self) -> ExpressionNode:
        if self.current()[0] == "OP" and self.current()[1] in ("+", "-"):
            op = self.eat("OP")[1]
            operand = self.factor()
            return UnaryOpNode(op, operand)
        return self.atom()

    def atom(self) -> ExpressionNode:
        tok = self.current()
        if tok[0] == "NUMBER":
            self.eat("NUMBER")
            return NumberNode(tok[1])
        elif tok[0] == "COLUMN":
            col_name = self.eat("COLUMN")[1]
            if col_name not in self.referenced_columns:
                self.referenced_columns.append(col_name)
            return ColumnNode(col_name)
        elif tok[0] == "LPAREN":
            self.eat("LPAREN")
            node = self.expr()
            self.eat("RPAREN")
            return node
        else:
            raise ValueError(f"Syntax error: expected number, column, or '(', got {tok[0]} '{tok[1]}'")


def validate_and_compile_expression(
    expression: str,
    allowed_columns: List[str],
    aggregation: str = "SUM"
) -> Tuple[str, List[str]]:
    """
    Validates a metric expression against allowed dataset columns and compiles it to safe SQL.

    Returns:
        (compiled_sql, list_of_referenced_columns)

    Examples:
        expression: "Unit Price * Quantity Ordered", aggregation: "SUM"
        -> ("SUM(`Unit Price` * `Quantity Ordered`)", ["Unit Price", "Quantity Ordered"])

        expression: "Total Sales Amount", aggregation: "SUM"
        -> ("SUM(`Total Sales Amount`)", ["Total Sales Amount"])

        expression: "Total Sales Amount / Quantity Ordered", aggregation: "SUM"
        -> ("SUM(`Total Sales Amount` / NULLIF(`Quantity Ordered`, 0))", ["Total Sales Amount", "Quantity Ordered"])
    """
    if not expression or not expression.strip():
        raise ValueError("Metric expression cannot be empty.")

    clean_expr = expression.strip()

    valid_aggs = {"SUM", "AVG", "COUNT", "COUNT_DISTINCT", "MIN", "MAX"}
    agg_upper = aggregation.strip().upper()
    if agg_upper not in valid_aggs:
        raise ValueError(f"Invalid aggregation '{aggregation}'. Allowed: {', '.join(sorted(valid_aggs))}")

    tokens = tokenize_expression(clean_expr, allowed_columns)
    parser = ExpressionParser(tokens)
    ast_root = parser.parse()
    raw_sql = ast_root.to_sql()

    # Wrap in aggregation function
    if isinstance(ast_root, ColumnNode):
        if agg_upper == "COUNT_DISTINCT":
            compiled_sql = f"COUNT(DISTINCT {raw_sql})"
        else:
            compiled_sql = f"{agg_upper}({raw_sql})"
    else:
        # For derived expressions:
        if agg_upper == "COUNT_DISTINCT":
            compiled_sql = f"COUNT(DISTINCT {raw_sql})"
        else:
            compiled_sql = f"{agg_upper}({raw_sql})" if isinstance(ast_root, NumberNode) else f"{agg_upper}{raw_sql}"

    return compiled_sql, parser.referenced_columns
